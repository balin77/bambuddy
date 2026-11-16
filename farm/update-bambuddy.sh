#!/usr/bin/env bash
# Update the farm Bambuddy container to the latest farm image, with backup and
# automatic rollback. Run on the print server (default: /opt/bambuddy).
#
# Steps: preflight -> remember running image (tag :farm-rollback) -> stop and
# back up volumes -> pull + up -d -> healthcheck (180 s) -> on failure roll
# back to the previous image (and optionally restore the data volume).
#
# Backups: one archive per volume in $BAMBUDDY_DIR/backups, named
#   <volume>-<UTC timestamp>.tar.gz
# The newest 10 archives per volume are kept; nothing else is ever deleted.
#
# Never uses `docker compose down -v` and never prunes volumes.
#
# Exit codes: 0 ok, 1 update failed but rolled back, 2 rollback failed,
#             3 preflight / usage error.

set -euo pipefail

BAMBUDDY_DIR="${BAMBUDDY_DIR:-/opt/bambuddy}"
SERVICE="${BAMBUDDY_SERVICE:-bambuddy}"
COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-bambuddy}"
DATA_VOLUME="${BAMBUDDY_DATA_VOLUME:-bambuddy_bambuddy_data}"
LOGS_VOLUME="${BAMBUDDY_LOGS_VOLUME:-bambuddy_bambuddy_logs}"
PORT="${BAMBUDDY_PORT:-8000}"
# Same endpoint the Dockerfile HEALTHCHECK uses.
HEALTH_PATH="${BAMBUDDY_HEALTH_PATH:-/health}"
HEALTH_TIMEOUT="${BAMBUDDY_HEALTH_TIMEOUT:-180}"
KEEP_BACKUPS="${BAMBUDDY_KEEP_BACKUPS:-10}"
ROLLBACK_IMAGE="${BAMBUDDY_ROLLBACK_IMAGE:-ghcr.io/balin77/bambuddy:farm-rollback}"
HELPER_IMAGE="${BAMBUDDY_HELPER_IMAGE:-alpine:3.20}"

export COMPOSE_PROJECT_NAME

DRY_RUN=0
NO_BACKUP=0
RESTORE_DB=0

usage() {
  cat <<USAGE
Usage: update-bambuddy.sh [--dry-run] [--no-backup] [--restore-db] [-h]

  --dry-run     Print what would happen; change nothing.
  --no-backup   Skip the volume backup (also disables --restore-db).
  --restore-db  If the update fails, also restore the data volume from the
                backup taken at the start (otherwise only done when the
                rolled-back container is still unhealthy).
  -h, --help    Show this help.

Environment: BAMBUDDY_DIR (default /opt/bambuddy), BAMBUDDY_SERVICE,
BAMBUDDY_DATA_VOLUME, BAMBUDDY_LOGS_VOLUME, BAMBUDDY_PORT,
BAMBUDDY_HEALTH_TIMEOUT, BAMBUDDY_KEEP_BACKUPS.
USAGE
}

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --no-backup) NO_BACKUP=1 ;;
    --restore-db) RESTORE_DB=1 ;;
    -h | --help) usage; exit 0 ;;
    *) echo "Unknown option: $arg" >&2; usage >&2; exit 3 ;;
  esac
done

BACKUP_DIR="$BAMBUDDY_DIR/backups"
LOG_FILE="$BACKUP_DIR/update.log"
TS="$(date -u +%Y%m%dT%H%M%SZ)"

log() {
  local line
  line="$(date '+%Y-%m-%d %H:%M:%S') $*"
  echo "$line"
  if [ "$DRY_RUN" -eq 0 ] && [ -d "$BACKUP_DIR" ]; then
    echo "$line" >>"$LOG_FILE"
  fi
}

die_preflight() {
  log "ERROR: $*"
  exit 3
}

# Run a state-changing command, or only print it in dry-run mode.
run() {
  if [ "$DRY_RUN" -eq 1 ]; then
    log "[dry-run] $*"
    return 0
  fi
  log "+ $*"
  "$@"
}

# ---------------------------------------------------------------- preflight
if [ "$DRY_RUN" -eq 0 ]; then
  mkdir -p "$BACKUP_DIR"
fi
log "=== Bambuddy farm update started (dry-run=$DRY_RUN no-backup=$NO_BACKUP restore-db=$RESTORE_DB) ==="

command -v docker >/dev/null 2>&1 || die_preflight "docker not found"
docker compose version >/dev/null 2>&1 || die_preflight "docker compose plugin not available"
command -v curl >/dev/null 2>&1 || die_preflight "curl not found"
[ -d "$BAMBUDDY_DIR" ] || die_preflight "$BAMBUDDY_DIR does not exist"
cd "$BAMBUDDY_DIR"
[ -f docker-compose.yml ] || die_preflight "docker-compose.yml missing in $BAMBUDDY_DIR"
[ -f docker-compose.override.yml ] || die_preflight "docker-compose.override.yml missing in $BAMBUDDY_DIR (copy farm/docker-compose.override.yml there)"

dc() { docker compose "$@"; }

CID="$(dc ps -q "$SERVICE" 2>/dev/null || true)"
if [ -z "$CID" ]; then
  log "WARN: no container found for service '$SERVICE' (first start?). No rollback image or backup possible."
fi

# ------------------------------------------ remember the running image
HAVE_ROLLBACK=0
if [ -n "$CID" ]; then
  OLD_IMAGE_ID="$(docker inspect -f '{{.Image}}' "$CID")"
  log "Running image ID: $OLD_IMAGE_ID"
  run docker tag "$OLD_IMAGE_ID" "$ROLLBACK_IMAGE"
  HAVE_ROLLBACK=1
fi

# -------------------------------------------------------------- backup
DATA_BACKUP=""
backup_volume() {
  local vol="$1" file="$2"
  run docker run --rm -v "$vol:/src:ro" -v "$BACKUP_DIR:/backup" "$HELPER_IMAGE" \
    tar czf "/backup/$file" -C /src .
}

prune_backups() {
  local prefix="$1" f
  [ "$DRY_RUN" -eq 1 ] && { log "[dry-run] keep newest $KEEP_BACKUPS of $BACKUP_DIR/$prefix-*.tar.gz"; return 0; }
  # Timestamps sort lexicographically; only our own archive names are touched.
  # shellcheck disable=SC2012
  ls -1 "$BACKUP_DIR/$prefix"-*.tar.gz 2>/dev/null | sort -r | tail -n +"$((KEEP_BACKUPS + 1))" |
    while IFS= read -r f; do
      log "Pruning old backup $f"
      rm -f -- "$f"
    done
}

if [ "$NO_BACKUP" -eq 1 ]; then
  log "Backup skipped (--no-backup)"
  RESTORE_DB=0
elif [ -n "$CID" ]; then
  # Stop first so the SQLite DB is consistent on disk.
  run dc stop "$SERVICE"
  DATA_BACKUP="$DATA_VOLUME-$TS.tar.gz"
  backup_volume "$DATA_VOLUME" "$DATA_BACKUP"
  backup_volume "$LOGS_VOLUME" "$LOGS_VOLUME-$TS.tar.gz"
  prune_backups "$DATA_VOLUME"
  prune_backups "$LOGS_VOLUME"
  log "Backups written to $BACKUP_DIR (suffix $TS)"
fi

# ----------------------------------------------------------- healthcheck
wait_healthy() {
  local deadline status code
  deadline=$((SECONDS + HEALTH_TIMEOUT))
  while [ "$SECONDS" -lt "$deadline" ]; do
    local cid
    cid="$(dc ps -q "$SERVICE" 2>/dev/null || true)"
    if [ -n "$cid" ]; then
      status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$cid" 2>/dev/null || echo unknown)"
      code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 5 "http://127.0.0.1:$PORT$HEALTH_PATH" 2>/dev/null || true)"
      log "health: container=$status http=${code:-000}"
      if [ "$status" = "healthy" ] && [ "$code" = "200" ]; then
        return 0
      fi
    else
      log "health: container not found yet"
    fi
    sleep 5
  done
  return 1
}

# -------------------------------------------------------------- rollback
restore_data_volume() {
  if [ -z "$DATA_BACKUP" ] || { [ "$DRY_RUN" -eq 0 ] && [ ! -f "$BACKUP_DIR/$DATA_BACKUP" ]; }; then
    log "ERROR: no data backup available to restore"
    return 1
  fi
  log "Restoring data volume $DATA_VOLUME from $DATA_BACKUP"
  run dc stop "$SERVICE"
  run docker run --rm -v "$DATA_VOLUME:/dst" -v "$BACKUP_DIR:/backup:ro" "$HELPER_IMAGE" \
    sh -c "find /dst -mindepth 1 -delete && tar xzf '/backup/$DATA_BACKUP' -C /dst"
  run dc up -d "$SERVICE"
}

rollback() {
  log "ROLLBACK: update failed"
  if [ "$HAVE_ROLLBACK" -ne 1 ]; then
    log "ERROR: no previous image known, cannot roll back"
    return 1
  fi
  run env BAMBUDDY_IMAGE="$ROLLBACK_IMAGE" docker compose up -d "$SERVICE" || true
  if [ "$RESTORE_DB" -eq 1 ]; then
    restore_data_volume_with_rollback_image || return 1
  fi
  if wait_healthy; then
    log "Rolled back to previous image; healthy."
    return 0
  fi
  log "Rolled-back container still unhealthy"
  if [ -n "$DATA_BACKUP" ] && [ "$RESTORE_DB" -eq 0 ]; then
    RESTORE_DB=1
    restore_data_volume_with_rollback_image || return 1
    wait_healthy
    return $?
  fi
  return 1
}

# Restore the data volume while keeping the rollback image selected.
restore_data_volume_with_rollback_image() {
  export BAMBUDDY_IMAGE="$ROLLBACK_IMAGE"
  restore_data_volume
  local rc=$?
  unset BAMBUDDY_IMAGE
  return "$rc"
}

# ------------------------------------------------------------ the update
update_ok=1
if ! run dc pull "$SERVICE"; then
  update_ok=0
elif ! run dc up -d "$SERVICE"; then
  update_ok=0
elif [ "$DRY_RUN" -eq 1 ]; then
  log "[dry-run] wait up to ${HEALTH_TIMEOUT}s for container healthy and HTTP 200 on 127.0.0.1:$PORT$HEALTH_PATH"
elif ! wait_healthy; then
  update_ok=0
fi

if [ "$update_ok" -eq 1 ]; then
  NEW_IMAGE_ID="$(docker inspect -f '{{.Image}}' "$(dc ps -q "$SERVICE")" 2>/dev/null || echo unknown)"
  log "=== Update finished OK. Running image ID: $NEW_IMAGE_ID ==="
  exit 0
fi

if rollback; then
  log "=== Update FAILED, rolled back to previous version ==="
  exit 1
fi
log "=== Update FAILED and ROLLBACK FAILED. Manual intervention required. Backups: $BACKUP_DIR ==="
exit 2
