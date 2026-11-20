"""The queue's "To do" list: what each waiting job needs a person for (#3615).

Two sources, neither parsed from ``waiting_reason`` text: the printers' live
state (plate to clear, sensor interlock, failed power-on) and the jobs' own
state (staged for a manual start, plus the structured filament holds the
scheduler records next to the words it writes). This module holds the shared
records and the pure part of the list; the route gathers the inputs.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field

from backend.app.utils.tray_ids import TrayLayout, external_slot_index, is_ams_ht_id

KIND_PRINT_PAUSED = "print_paused"
KIND_PLATE_CLEAR = "plate_clear"
KIND_SENSOR_INTERLOCK = "sensor_interlock"
KIND_POWER_ON_FAILED = "power_on_failed"
KIND_LOAD_FILAMENT = "load_filament"
KIND_START_STAGED = "start_staged"

# Order of the entries inside one group.
_KIND_ORDER = (
    KIND_PRINT_PAUSED,
    KIND_PLATE_CLEAR,
    KIND_SENSOR_INTERLOCK,
    KIND_POWER_ON_FAILED,
    KIND_LOAD_FILAMENT,
    KIND_START_STAGED,
)


@dataclass(frozen=True)
class TodoFilament:
    """One filament a job waits for. ``color`` is "#RRGGBB" or empty.

    ``nozzle`` is the extruder a dual-nozzle file wants it on, as the waiting
    text names it: 0 the right nozzle, 1 the left, None when the file names none.
    """

    type: str
    color: str
    color_name: str = ""
    no_stock: bool = False
    nozzle: int | None = None


@dataclass(frozen=True)
class FilamentHold:
    """Why one job is held on filament, for one printer.

    ``printer_id`` None with ``target_model`` set is a model job whose printer
    set is not known (it is listed under "Any <model>").
    """

    item_id: int
    printer_id: int | None
    target_model: str | None
    filaments: tuple[TodoFilament, ...]


def todo_filament_from_requirement(req: Mapping) -> TodoFilament:
    """A TodoFilament from a requirement or override dict (type/color/color_name/nozzle_id)."""
    nozzle = req.get("nozzle_id")
    return TodoFilament(
        type=str(req.get("type") or "").upper(),
        color=normalize_hex(req.get("color")),
        color_name=str(req.get("color_name") or ""),
        nozzle=nozzle if type(nozzle) is int and nozzle in (0, 1) else None,
    )


def normalize_hex(value: object) -> str:
    """ "#RRGGBB" from "RRGGBB", "#rrggbbaa" and the like; empty when it is no colour."""
    if not isinstance(value, str):
        return ""
    raw = value.strip().lstrip("#")[:6]
    if len(raw) != 6 or any(c not in "0123456789abcdefABCDEF" for c in raw):
        return ""
    return f"#{raw.upper()}"


@dataclass
class TodoJob:
    """A pending job as the list needs it."""

    id: int
    name: str
    # Printers the job could go to: its pinned printer, or every printer of
    # its model (and location) that its creator may use and the caller may see.
    printer_ids: frozenset[int]
    # The pinned printer, None for a model job.
    pinned_id: int | None
    # Lower-case model of a model job, used to group holds that name no printer.
    model_key: str | None
    model_label: str | None
    manual_start: bool
    # Whether the caller may start it now (only read for staged jobs).
    can_start: bool = False


CAUSE_RUNOUT_AMS = "runout_ams"
CAUSE_RUNOUT_EXTERNAL = "runout_external"
CAUSE_ERROR = "error"
CAUSE_PAUSED = "paused"

# AMS per-slot runout (07XX_8011, units 0-7 and the 07FF placeholder) and the
# external spool's runout, as the printer card's runout guidance reads them (#2587).
_AMS_RUNOUT_CODES = frozenset({f"07{unit:02X}_8011" for unit in (*range(8), 0xFF)})
_EXTERNAL_RUNOUT_CODE = "0300_8004"


@dataclass(frozen=True)
class PausedSlot:
    """A slot a paused print names, with the field names of the filament hints' slots (#3634).

    ``type`` and ``color`` are what the slot's tray reports now; empty for an empty slot.
    """

    ams_id: int
    tray_id: int
    is_ht: bool
    is_external: bool
    ams_type: int | None
    type: str = ""
    color: str = ""
    tray_info_idx: str = ""
    tray_sub_brands: str = ""


@dataclass(frozen=True)
class PauseCause:
    """Why a printer sits paused, as far as its faults and slots say."""

    cause: str = CAUSE_PAUSED
    ran_out: PausedSlot | None = None
    expected: PausedSlot | None = None
    error_code: str | None = None
    error_description: str | None = None
    more_errors: int = 0


@dataclass(frozen=True)
class PausedInfo:
    """A paused print as the list shows it (#3648)."""

    job_name: str | None
    progress: int | None
    remaining_minutes: int | None
    cause: PauseCause = field(default_factory=PauseCause)


def _fault_short_code(fault: Mapping) -> str:
    attr = fault.get("attr")
    code = fault.get("code")
    try:
        number = int(code.replace("0x", "") or "0", 16) if isinstance(code, str) else int(code or 0)
        module = (int(attr or 0) >> 16) & 0xFFFF
    except (TypeError, ValueError):
        return ""
    return f"{module:04X}_{number & 0xFFFF:04X}"


def _fault_display_code(fault: Mapping) -> str:
    """The code as the printer screen writes it: four groups for an hms[] fault, two for a print_error."""
    full = fault.get("full_code")
    if isinstance(full, str) and len(full) == 16:
        return "-".join(full[i : i + 4] for i in range(0, 16, 4))
    return _fault_short_code(fault).replace("_", "-")


def _counts_as_fault(fault: Mapping) -> bool:
    """A fault the printer card counts as a problem (``hms_fault_counts``, on a status dict).

    Text or actions at a real level; an hms[] notice (level 3, 16-character
    code) without actions does not count, a print_error prompt at that level does.
    """
    severity = fault.get("severity")
    if not isinstance(severity, int) or severity < 1:
        return False
    if fault.get("actions"):
        return True
    is_hms_notice = len(fault.get("full_code") or "") == 16 and severity == 3
    return bool(fault.get("description")) and not is_hms_notice


def pause_cause(
    faults: Iterable[Mapping],
    expected: PausedSlot | None = None,
    ran_out: PausedSlot | None = None,
) -> PauseCause:
    """Why a PAUSE-state printer waits: a runout, another fault, or no reason.

    A runout wins over any other fault. ``more_errors`` counts the other faults
    that count as problems.
    """
    listed = [f for f in faults if isinstance(f, Mapping)]
    codes = [_fault_short_code(f) for f in listed]
    if any(code in _AMS_RUNOUT_CODES for code in codes):
        others = sum(
            1 for f, c in zip(listed, codes, strict=True) if c not in _AMS_RUNOUT_CODES and _counts_as_fault(f)
        )
        return PauseCause(CAUSE_RUNOUT_AMS, ran_out=ran_out, expected=expected, more_errors=others)
    if _EXTERNAL_RUNOUT_CODE in codes:
        others = sum(
            1 for f, c in zip(listed, codes, strict=True) if c != _EXTERNAL_RUNOUT_CODE and _counts_as_fault(f)
        )
        return PauseCause(CAUSE_RUNOUT_EXTERNAL, more_errors=others)
    severe = [f for f in listed if _counts_as_fault(f)]
    if not severe:
        return PauseCause()
    # Severity 1 (error) before 2 (warning) before a level-3 print_error prompt; the first reported wins a tie.
    top = min(severe, key=lambda f: f["severity"])
    return PauseCause(
        CAUSE_ERROR,
        error_code=_fault_display_code(top),
        error_description=top.get("description") or None,
        more_errors=len(severe) - 1,
    )


def paused_slot(status: Mapping, tray_id: int | None, layout: TrayLayout) -> PausedSlot | None:
    """The slot of global tray ``tray_id`` with what its tray reports, from a printer status dict."""
    if tray_id is None:
        return None
    vt_trays = [vt for vt in status.get("vt_tray") or [] if isinstance(vt, Mapping)]
    tray: Mapping | None
    if layout.is_external(tray_id):
        tray = next((vt for vt in vt_trays if vt.get("id") == tray_id), None)
        ams_id, slot_id, is_ht, is_external, ams_type = -1, external_slot_index(tray_id), False, True, None
    else:
        ams_id, slot_id = layout.slot_key(tray_id)
        tray = None
        for unit in status.get("ams") or []:
            if isinstance(unit, Mapping) and unit.get("id") == ams_id:
                tray = next((t for t in unit.get("tray") or [] if t.get("id") == slot_id), None)
                break
        is_ht, is_external, ams_type = is_ams_ht_id(ams_id), False, int(layout.ams_type(ams_id))
    kind = str((tray or {}).get("tray_type") or "")
    return PausedSlot(
        ams_id=ams_id,
        tray_id=slot_id,
        is_ht=is_ht,
        is_external=is_external,
        ams_type=ams_type,
        type=kind,
        color=normalize_hex((tray or {}).get("tray_color")) if kind else "",
        tray_info_idx=str((tray or {}).get("tray_info_idx") or ""),
        tray_sub_brands=str((tray or {}).get("tray_sub_brands") or ""),
    )


def paused_info_from_status(
    status: Mapping, layout: TrayLayout, job_name: str | None, cause: Callable[[PauseCause], PauseCause] | None = None
) -> PausedInfo:
    """A PAUSE-state printer's status dict (``printer_state_to_dict``) as the list's record."""
    detected = pause_cause(
        status.get("hms_errors") or [],
        expected=paused_slot(status, status.get("expected_tray"), layout),
        ran_out=paused_slot(status, status.get("previous_tray"), layout),
    )
    progress = status.get("progress")
    remaining = status.get("remaining_time")
    return PausedInfo(
        job_name=job_name,
        progress=int(progress) if isinstance(progress, (int, float)) else None,
        remaining_minutes=int(remaining) if isinstance(remaining, (int, float)) and remaining >= 0 else None,
        cause=cause(detected) if cause is not None else detected,
    )


# How long a stored cause outlives the last time the status yielded it. It covers
# the HMS list being rebuilt momentarily empty by a status payload; a cause that
# stays gone longer was cleared on the printer, so the current one wins.
CAUSE_HOLD_SECONDS = 20.0


class PauseEpisodes:
    """Keeps the cause of each printer's current pause while its faults are rebuilt.

    The printer rebuilds its fault list with every status payload, so a runout
    can read as "no reason" for a moment. The list entry depends only on the
    printer being paused; this keeps the last real cause of the same episode
    (the printer and its job) for ``CAUSE_HOLD_SECONDS`` after it was last seen,
    and drops it as soon as the printer is seen out of PAUSE, so a later pause
    of the same job never inherits it.
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        # printer id -> (episode, cause, when the status last yielded that cause)
        self._seen: dict[int, tuple[str, PauseCause, float]] = {}

    def resolve(self, printer_id: int, episode: str, current: PauseCause) -> PauseCause:
        now = self._clock()
        stored = self._seen.get(printer_id)
        if current.cause != CAUSE_PAUSED:
            self._seen[printer_id] = (episode, current, now)
            return current
        if stored is not None and stored[0] == episode and now - stored[2] <= CAUSE_HOLD_SECONDS:
            return stored[1]
        self._seen.pop(printer_id, None)
        return current

    def observe_not_paused(self, printer_id: int) -> None:
        """The printer was seen outside PAUSE: whatever it stored belonged to an earlier pause."""
        self._seen.pop(printer_id, None)

    def prune(self, still_paused: Callable[[int], bool]) -> None:
        """Forget printers that are not paused any more."""
        for printer_id in [pid for pid in self._seen if not still_paused(pid)]:
            self.observe_not_paused(printer_id)


@dataclass
class _Group:
    printer_id: int | None
    printer_name: str
    target_model: str | None
    first_index: int
    entries: dict[tuple, dict] = field(default_factory=dict)


def _sorted(filaments: Iterable[TodoFilament]) -> tuple[TodoFilament, ...]:
    # Without a nozzle first, then right (0) before left (1).
    return tuple(sorted(filaments, key=lambda f: (f.type, f.color, f.color_name, -1 if f.nozzle is None else f.nozzle)))


def _fil_key(filaments: Iterable[TodoFilament]) -> tuple:
    return tuple((f.type, f.color, f.nozzle) for f in _sorted(filaments))


def _slot_dict(slot: PausedSlot | None) -> dict | None:
    return None if slot is None else {f: getattr(slot, f) for f in PausedSlot.__dataclass_fields__}


def _paused_dict(info: PausedInfo) -> dict:
    cause = info.cause
    return {
        "job_name": info.job_name,
        "progress": info.progress,
        "remaining_minutes": info.remaining_minutes,
        "cause": cause.cause,
        "ran_out": _slot_dict(cause.ran_out),
        "expected": _slot_dict(cause.expected),
        "error": (
            {"code": cause.error_code, "description": cause.error_description} if cause.cause == CAUSE_ERROR else None
        ),
        "more_errors": cause.more_errors,
    }


def build_todo(
    jobs: list[TodoJob],
    printers: Mapping[int, str],
    holds: Mapping[int, list[FilamentHold]],
    plate_clear_ids: Iterable[int],
    interlock: Mapping[int, str],
    power_failed_ids: Iterable[int],
    *,
    paused: Mapping[int, PausedInfo] | None = None,
) -> dict:
    """The response of GET /queue/todo.

    ``jobs`` are the visible pending jobs in queue order; ``printers`` maps the
    visible printer ids to their names. Printer entries need a waiting job
    that could go to that printer, except for a paused print: it is listed
    whether or not a job waits (#3648). ``paused`` maps a printer id to its
    paused print.
    """
    groups: dict[tuple, _Group] = {}
    index_of = {job.id: i for i, job in enumerate(jobs)}

    def group_for(printer_id: int | None, model_key: str | None, model_label: str | None, index: int) -> _Group:
        key = ("p", printer_id) if printer_id is not None else ("m", model_key)
        group = groups.get(key)
        if group is None:
            name = printers.get(printer_id, "") if printer_id is not None else (model_label or "")
            group = groups[key] = _Group(printer_id, name, None if printer_id is not None else model_label, index)
        else:
            group.first_index = min(group.first_index, index)
        return group

    def add(group: _Group, kind: str, subkey: tuple, job: TodoJob, **extra) -> None:
        entry = group.entries.setdefault(
            (kind, subkey), {"kind": kind, "jobs": [], "detail": None, "printers": [], **extra}
        )
        if all(j["id"] != job.id for j in entry["jobs"]):
            entry["jobs"].append(
                {"id": job.id, "name": job.name, "can_start": kind == KIND_START_STAGED and job.can_start}
            )

    # A paused print waits for a person whatever is queued, so its group needs no
    # job and sorts to the top of the list, waiting jobs or not.
    for pid, info in (paused or {}).items():
        if pid not in printers:
            continue
        waiting = [job for job in jobs if pid in job.printer_ids]
        group = group_for(pid, None, None, -1)
        group.entries.setdefault(
            (KIND_PRINT_PAUSED, ()),
            {"kind": KIND_PRINT_PAUSED, "jobs": [], "detail": None, "printers": [], "paused": _paused_dict(info)},
        )
        for job in waiting:
            add(group, KIND_PRINT_PAUSED, (), job)

    # Printer-state entries, one per printer, listing the jobs that could go there.
    printer_kinds: list[tuple[str, int, str | None]] = []
    printer_kinds += [(KIND_PLATE_CLEAR, pid, None) for pid in plate_clear_ids]
    printer_kinds += [(KIND_SENSOR_INTERLOCK, pid, reason) for pid, reason in interlock.items()]
    printer_kinds += [(KIND_POWER_ON_FAILED, pid, None) for pid in power_failed_ids]
    for kind, pid, detail in printer_kinds:
        if pid not in printers:
            continue
        waiting = [job for job in jobs if pid in job.printer_ids]
        if not waiting:
            continue
        group = group_for(pid, None, None, index_of[waiting[0].id])
        for job in waiting:
            add(group, kind, (), job)
        group.entries[(kind, ())]["detail"] = detail or None

    for job in jobs:
        index = index_of[job.id]
        holds_of_job = holds.get(job.id, [])
        if job.pinned_id is not None:
            if job.pinned_id not in printers:
                continue
            group = group_for(job.pinned_id, None, None, index)
            for hold in holds_of_job:
                add(group, KIND_LOAD_FILAMENT, _fil_key(hold.filaments), job, _filaments=_sorted(hold.filaments))
        else:
            # A model job's per-printer holds become one entry: the printers
            # that miss the fewest filaments are where loading them lets it start.
            visible = [h for h in holds_of_job if h.printer_id in printers]
            if visible:
                fewest = min(len(h.filaments) for h in visible)
                by_set: dict[tuple, tuple[tuple[TodoFilament, ...], set[int]]] = {}
                for hold in visible:
                    if len(hold.filaments) == fewest:
                        sets = by_set.setdefault(_fil_key(hold.filaments), (_sorted(hold.filaments), set()))
                        assert hold.printer_id is not None
                        sets[1].add(hold.printer_id)
                for key, (fils, ids) in by_set.items():
                    add(
                        group_for(None, job.model_key, job.model_label, index),
                        KIND_LOAD_FILAMENT,
                        (key, tuple(sorted(ids))),
                        job,
                        _filaments=fils,
                        printers=[{"id": pid, "name": printers[pid]} for pid in sorted(ids)],
                    )
            else:
                for hold in holds_of_job:
                    if hold.printer_id is None:
                        add(
                            group_for(None, job.model_key, job.model_label, index),
                            KIND_LOAD_FILAMENT,
                            (_fil_key(hold.filaments), ()),
                            job,
                            _filaments=_sorted(hold.filaments),
                        )
        if job.manual_start:
            group = group_for(job.pinned_id, job.model_key, job.model_label, index)
            add(group, KIND_START_STAGED, (), job)

    out_groups = []
    count = 0
    for group in sorted(groups.values(), key=lambda g: g.first_index):
        entries = []
        for kind in _KIND_ORDER:
            for (k, _sub), entry in group.entries.items():
                if k != kind:
                    continue
                fils = entry.pop("_filaments", ())
                entry["filaments"] = [
                    {
                        "type": f.type,
                        "color": f.color,
                        "color_name": f.color_name,
                        "no_stock": f.no_stock,
                        "nozzle": f.nozzle,
                    }
                    for f in fils
                ]
                entries.append(entry)
        if not entries:
            continue
        count += len(entries)
        out_groups.append(
            {
                "printer_id": group.printer_id,
                "printer_name": group.printer_name,
                "target_model": group.target_model,
                "entries": entries,
            }
        )
    return {"count": count, "groups": out_groups}
