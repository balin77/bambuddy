"""The queue's "To do" list: what each waiting job needs a person for (#3615).

Two sources, neither parsed from ``waiting_reason`` text: the printers' live
state (plate to clear, sensor interlock, failed power-on) and the jobs' own
state (staged for a manual start, plus the structured filament holds the
scheduler records next to the words it writes). This module holds the shared
records and the pure part of the list; the route gathers the inputs.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass, field, replace

KIND_PLATE_CLEAR = "plate_clear"
KIND_PLATE_CHANGER_EMPTY = "plate_changer_empty"
KIND_SENSOR_INTERLOCK = "sensor_interlock"
KIND_POWER_ON_FAILED = "power_on_failed"
KIND_LOAD_FILAMENT = "load_filament"
KIND_START_STAGED = "start_staged"

# Where a missing filament can go (#3634).
HINT_FREE = "free"
HINT_REPLACEABLE = "replaceable"
HINT_ALL_NEEDED = "all_needed"

# Order of the entries inside one group.
_KIND_ORDER = (
    KIND_PLATE_CLEAR,
    KIND_PLATE_CHANGER_EMPTY,
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
    # What the stock check of #3590 needs; not part of the response.
    tray_info_idx: str = field(default="", compare=False)
    forced: bool = field(default=False, compare=False)


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


@dataclass(frozen=True)
class HintSlot:
    """One slot a filament can go into: empty, or loaded with a filament no waiting job needs.

    ``nozzle`` is "left" or "right" on a dual-nozzle printer without a
    Filament Track Switch, else None. ``type`` and ``color`` are empty for a
    free slot.
    """

    ams_id: int
    tray_id: int
    is_ht: bool
    is_external: bool
    ams_type: int | None
    nozzle: str | None
    type: str = ""
    color: str = ""
    tray_info_idx: str = ""
    tray_sub_brands: str = ""


@dataclass(frozen=True)
class NozzleHint:
    """The hint for the filaments that go on one nozzle."""

    nozzle: str
    state: str
    slots: tuple[HintSlot, ...]


@dataclass(frozen=True)
class SlotHint:
    """Where the missing filaments of one printer can go, noted by the scheduler's pass.

    ``state`` is ``free`` (an empty slot is reported), ``replaceable`` (every
    slot is loaded, ``slots`` holds the ones no waiting job needs) or
    ``all_needed``, over every slot of the printer. ``by_nozzle`` is filled on
    a dual-nozzle printer without a Filament Track Switch: one part per nozzle
    that has a slot. ``unknown_job_ids`` are the waiting jobs whose filaments
    could not be read; the route counts the ones its caller may see. No job is
    named in the response.
    """

    printer_id: int
    state: str
    slots: tuple[HintSlot, ...] = ()
    unknown_job_ids: tuple[int, ...] = ()
    by_nozzle: tuple[NozzleHint, ...] = ()

    @property
    def unknown_jobs(self) -> int:
        return len(self.unknown_job_ids)


def todo_filament_from_requirement(req: Mapping) -> TodoFilament:
    """A TodoFilament from a requirement or override dict (type/color/color_name/nozzle_id)."""
    nozzle = req.get("nozzle_id")
    return TodoFilament(
        type=str(req.get("type") or "").upper(),
        color=normalize_hex(req.get("color")),
        color_name=str(req.get("color_name") or ""),
        nozzle=nozzle if type(nozzle) is int and nozzle in (0, 1) else None,
        tray_info_idx=str(req.get("tray_info_idx") or ""),
        forced=bool(req.get("force_color_match")),
    )


def merge_todo_filaments(into: list[TodoFilament], more: Iterable[TodoFilament]) -> None:
    """Add the filaments of ``more`` that ``into`` lacks, in place.

    ``forced`` and ``tray_info_idx`` are not compared, so a filament already
    there stands for its twin; the forced twin wins (the flag is OR-ed), or the
    stock flag of the forced one would be lost (#3615).
    """
    for f in more:
        for i, known in enumerate(into):
            if known == f:
                if f.forced and not known.forced:
                    into[i] = replace(known, forced=True, tray_info_idx=f.tray_info_idx or known.tray_info_idx)
                break
        else:
            into.append(f)


def priority_state(has_priority: bool, hours: int | None) -> tuple[str, int | None]:
    """("has_priority", None) or ("priority_in", hours): a job's place in the filament wait (#3587)."""
    return ("has_priority", None) if has_priority else ("priority_in", hours)


def _more_urgent(candidate: tuple[str, int | None], current: tuple[str, int | None] | None) -> bool:
    """Whether ``candidate`` beats ``current``: having priority, else the fewest hours."""
    if current is None or current[0] == "priority_in" and candidate[0] == "has_priority":
        return True
    return current[0] == "priority_in" and candidate[0] == "priority_in" and (candidate[1] or 0) < (current[1] or 0)


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


def _slot_dict(slot: HintSlot) -> dict:
    return {
        "ams_id": slot.ams_id,
        "tray_id": slot.tray_id,
        "is_ht": slot.is_ht,
        "is_external": slot.is_external,
        "ams_type": slot.ams_type,
        "nozzle": slot.nozzle,
        "type": slot.type,
        "color": slot.color,
        "tray_info_idx": slot.tray_info_idx,
        "tray_sub_brands": slot.tray_sub_brands,
    }


_HINT_RANK = {HINT_FREE: 0, HINT_REPLACEABLE: 1, HINT_ALL_NEEDED: 2}


def _hint_dict(hint: SlotHint, filaments: Iterable[TodoFilament], visible_ids: Collection[int]) -> dict | None:
    """A printer's hint as one entry shows it (#3634), or None when it has nothing for the entry.

    On a dual-nozzle printer without a Filament Track Switch the hint has a
    part per nozzle. An entry whose filaments all name a nozzle is built from
    the parts of those nozzles alone, so it is never offered a slot of the
    other one; when none of its nozzles has a slot, there is no hint. A
    filament that names no nozzle may take any tray, as the matcher reads it,
    so such an entry shows the printer's hint over every slot.

    ``unknown_jobs`` counts only the waiting jobs in ``visible_ids``.
    """
    state, slots, parts = hint.state, hint.slots, ()
    if hint.by_nozzle:
        nozzles = {f.nozzle for f in filaments}
        if None not in nozzles:
            labels = {"left" if n == 1 else "right" for n in nozzles}
            parts = tuple(p for p in hint.by_nozzle if p.nozzle in labels)
            if not parts:
                return None
            state = min((p.state for p in parts), key=_HINT_RANK.__getitem__)
            slots = tuple(slot for p in parts if p.state == state for slot in p.slots)
    return {
        "state": state,
        "slots": [_slot_dict(slot) for slot in slots],
        "unknown_jobs": sum(1 for job_id in hint.unknown_job_ids if job_id in visible_ids),
        "by_nozzle": [{"nozzle": p.nozzle, "state": p.state, "slots": [_slot_dict(x) for x in p.slots]} for p in parts],
    }


def build_todo(
    jobs: list[TodoJob],
    printers: Mapping[int, str],
    holds: Mapping[int, list[FilamentHold]],
    plate_clear_ids: Iterable[int],
    interlock: Mapping[int, str],
    power_failed_ids: Iterable[int],
    plate_changer_empty: Mapping[int, int | None] | None = None,
    priorities: Mapping[int, tuple[str, int | None]] | None = None,
    slot_hints: Mapping[int, SlotHint] | None = None,
) -> dict:
    """The response of GET /queue/todo.

    ``jobs`` are the visible pending jobs in queue order; ``printers`` maps the
    visible printer ids to their names. Printer entries need a waiting job
    that could go to that printer. ``plate_changer_empty`` maps the printers
    whose plate changer has no plate left to their capacity (#3575);
    ``priorities`` maps a job to its place in the loaded-filament-first wait
    (#3587). ``slot_hints`` are the scheduler's, by
    printer id: a load entry carries its printer's (a model entry one per
    printer it lists), and never names a job (#3634).
    """
    slot_hints = slot_hints or {}
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
            (kind, subkey),
            {
                "kind": kind,
                "jobs": [],
                "detail": None,
                "printers": [],
                "priority": None,
                "priority_hours": None,
                "plate_capacity": None,
                **extra,
            },
        )
        if kind == KIND_LOAD_FILAMENT and priorities and job.id in priorities:
            state = priorities[job.id]
            if _more_urgent(state, (entry["priority"], entry["priority_hours"]) if entry["priority"] else None):
                entry["priority"], entry["priority_hours"] = state
        if all(j["id"] != job.id for j in entry["jobs"]):
            entry["jobs"].append(
                {"id": job.id, "name": job.name, "can_start": kind == KIND_START_STAGED and job.can_start}
            )

    # Printer-state entries, one per printer, listing the jobs that could go there.
    printer_kinds: list[tuple[str, int, str | None]] = []
    printer_kinds += [(KIND_PLATE_CLEAR, pid, None) for pid in plate_clear_ids]
    printer_kinds += [(KIND_PLATE_CHANGER_EMPTY, pid, None) for pid in (plate_changer_empty or {})]
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
        if kind == KIND_PLATE_CHANGER_EMPTY:
            group.entries[(kind, ())]["plate_capacity"] = (plate_changer_empty or {}).get(pid)

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
                if kind == KIND_LOAD_FILAMENT:
                    if group.printer_id is not None:
                        hint = slot_hints.get(group.printer_id)
                        entry["slot_hint"] = _hint_dict(hint, fils, index_of) if hint else None
                    else:
                        entry["slot_hints"] = [
                            {"printer_id": p["id"], **shown}
                            for p in entry["printers"]
                            if p["id"] in slot_hints
                            and (shown := _hint_dict(slot_hints[p["id"]], fils, index_of)) is not None
                        ]
                entries.append(entry)
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
