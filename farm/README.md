# Farm deployment

Files for running the farm build (`ghcr.io/balin77/bambuddy:farm`, built from the
`farm` branch by `.github/workflows/farm-image.yml`) on the print server while
keeping the upstream `docker-compose.yml` untouched.

## First-time setup (on the server, in `/opt/bambuddy`)

```bash
cd /opt/bambuddy
cp /path/to/farm/docker-compose.override.yml .
cp /path/to/farm/update-bambuddy.sh . && chmod +x update-bambuddy.sh
./update-bambuddy.sh --dry-run    # check what it will do
./update-bambuddy.sh
```

The compose project name must stay `bambuddy` (run from `/opt/bambuddy`, no `-p`),
so the existing volumes `bambuddy_bambuddy_data` and `bambuddy_bambuddy_logs` are reused.
**Never run `docker compose down -v`.**

## Regular updates

```bash
cd /opt/bambuddy && ./update-bambuddy.sh
```

The script tags the running image as `:farm-rollback`, stops the container, backs
up both volumes to `/opt/bambuddy/backups/<volume>-<timestamp>.tar.gz` (newest 10
per volume kept), pulls and starts the new image, and waits up to 180 s for
`healthy` plus HTTP 200 on `http://127.0.0.1:8000/health`. Everything is logged to
`/opt/bambuddy/backups/update.log`.

Options: `--dry-run`, `--no-backup`, `--restore-db`, `-h`.
Exit codes: 0 ok, 1 failed but rolled back, 2 rollback failed, 3 preflight error.

## Rollback

Automatic when the health check fails: the container is recreated from
`:farm-rollback`. If it is still unhealthy (or `--restore-db` was given) the data
volume is also restored from the backup taken at the start of the run.

Manual rollback to the previous image:

```bash
BAMBUDDY_IMAGE=ghcr.io/balin77/bambuddy:farm-rollback docker compose up -d
```

Manual restore of the data volume from an archive:

```bash
docker compose stop bambuddy
docker run --rm -v bambuddy_bambuddy_data:/dst -v /opt/bambuddy/backups:/backup:ro alpine \
  sh -c 'find /dst -mindepth 1 -delete && tar xzf /backup/<archive>.tar.gz -C /dst'
docker compose up -d
```

## Back to pure upstream

```bash
cd /opt/bambuddy
rm docker-compose.override.yml
docker compose pull && docker compose up -d
```

Farm migrations are additive; they leave at most unused columns behind.

## Do not use the in-app update button

It points at upstream (`maziggy/bambuddy`). Updates go through `update-bambuddy.sh` only.
