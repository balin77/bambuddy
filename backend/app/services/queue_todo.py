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

from backend.app.utils.color_utils import colors_are_similar
from backend.app.utils.filament_types import canonical_filament_type

KIND_PLATE_CLEAR = "plate_clear"
KIND_SENSOR_INTERLOCK = "sensor_interlock"
KIND_POWER_ON_FAILED = "power_on_failed"
KIND_LOAD_FILAMENT = "load_filament"
KIND_START_STAGED = "start_staged"

# Where a missing filament can go (#3634).
HINT_FREE = "free"
HINT_REPLACEABLE = "replaceable"
HINT_ALL_NEEDED = "all_needed"
# A spool the job needs holds too little: that spool is the one to replace.
HINT_REPLACE = "replace"

# Order of the entries inside one group.
_KIND_ORDER = (
    KIND_PLATE_CLEAR,
    KIND_SENSOR_INTERLOCK,
    KIND_POWER_ON_FAILED,
    KIND_LOAD_FILAMENT,
    KIND_START_STAGED,
)


@dataclass(frozen=True)
class ShortTray:
    """A tray whose spool has too little filament for the job (#3634).

    ``remaining_grams`` is None when the amount is not known.
    """

    ams_id: int
    tray_id: int
    remaining_grams: float | None = None


@dataclass(frozen=True)
class TodoFilament:
    """One filament a job waits for. ``color`` is "#RRGGBB" or empty.

    ``nozzle`` is the extruder a dual-nozzle file wants it on, as the waiting
    text names it: 0 the right nozzle, 1 the left, None when the file names none.

    ``short`` marks a filament that is loaded but in too little amount: it is
    not missing, a spool holds less than the job needs. ``short_trays`` are the
    trays counted for it (the mapped one, and with AMS Filament Backup every
    tray pooled with it) and ``required_grams`` what the job prints of it.
    ``tray_info_idx`` and ``forced`` (a forced colour match) say which loaded
    trays count as this filament. None of these five takes part in equality, so
    a list of filaments compares as it did before they existed (#3634).
    """

    type: str
    color: str
    color_name: str = ""
    no_stock: bool = False
    nozzle: int | None = None
    short: bool = field(default=False, compare=False)
    short_trays: tuple[ShortTray, ...] = field(default=(), compare=False)
    required_grams: float | None = field(default=None, compare=False)
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
    # Only on a slot of a "replace" hint: what the spool has left, when known.
    remaining_grams: float | None = None


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
    # Every loaded slot of the printer, whatever a job needs. Not shown as it
    # is: an entry whose filament is short looks its trays up here.
    loaded: tuple[HintSlot, ...] = ()

    @property
    def unknown_jobs(self) -> int:
        return len(self.unknown_job_ids)


@dataclass(frozen=True)
class PrepareEntry:
    """What to prepare for one of a printer's next jobs (#3640).

    ``position`` is 1 for the next job that misses filament, 2 for the one
    after. ``filaments`` are the ones it misses; ``hint`` says where they can
    go without touching the running print, a nearer job or the printer's
    filament backup. The job is named by the route, for the callers who may
    see it.
    """

    printer_id: int
    item_id: int
    position: int
    filaments: tuple[TodoFilament, ...]
    hint: SlotHint | None


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


def tray_fits_filament(slot: HintSlot, filament: TodoFilament) -> bool:
    """Whether a loaded tray is a spool of ``filament``, as the dispatch matcher reads it (#3634).

    The same canonical type, and a colour that is the same (exact when the
    filament forces the colour match) or similar (the matcher's per-channel
    threshold); and when both sides name a filament preset (``tray_info_idx``),
    the same one. A tray that fits is not offered as a place to load that
    filament: the matcher would use it. See ``_match_filaments_to_slots`` and
    ``_force_color_misses``, which a test holds this against.

    Intentionally stricter than the matcher, so that it errs towards not
    offering a tray the matcher might still use. Known edge cases: a
    non-forced preference override is counted by
    ``_count_override_color_matches`` as an exact match only, while this treats
    a similar colour as fitting; limits that come from the job's creator
    (filaments they may not use) are not known here; and in an entry that names
    nozzles, a same-type tray on the other nozzle is judged by type and colour
    alone, as the nozzle is not part of the test.
    """
    if not slot.type or canonical_filament_type(slot.type.upper()) != canonical_filament_type(filament.type.upper()):
        return False
    if filament.tray_info_idx and slot.tray_info_idx and filament.tray_info_idx != slot.tray_info_idx:
        return False
    want = filament.color.replace("#", "").lower()[:6]
    have = slot.color.replace("#", "").lower()[:6]
    if want == have:
        return True
    return not filament.forced and colors_are_similar(slot.color, filament.color)


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
    # A short spool and a missing one of the same filament are two things to do.
    return tuple((f.type, f.color, f.nozzle, f.short) for f in _sorted(filaments))


def _identity(f: TodoFilament) -> tuple:
    # Equality ignores the short fields; two short rows of one filament on
    # different trays are still two rows.
    return (f.type, f.color, f.nozzle, f.short, tuple(sorted((t.ams_id, t.tray_id) for t in f.short_trays)))


def unique_filaments(*groups: Iterable[TodoFilament]) -> list[TodoFilament]:
    """The filaments of all ``groups`` without repeats, a repeat being the same filament on the same trays (#3634)."""
    seen: set[tuple] = set()
    out: list[TodoFilament] = []
    for group in groups:
        for f in group:
            if (key := _identity(f)) not in seen:
                seen.add(key)
                out.append(f)
    return out


def _merge_short(base: tuple[TodoFilament, ...], more: tuple[TodoFilament, ...]) -> tuple[TodoFilament, ...]:
    """``base`` with the short trays of ``more`` (the same filaments, in the same order) added."""
    if len(base) != len(more):
        return base
    merged = []
    for a, b in zip(base, more, strict=True):
        if a.short and b.short and (extra := [t for t in b.short_trays if t not in a.short_trays]):
            a = replace(a, short_trays=a.short_trays + tuple(extra))
        if a.short and b.short:
            # The most any of the jobs needs, whether or not trays were added.
            grams = [g for g in (a.required_grams, b.required_grams) if g is not None]
            a = replace(a, required_grams=max(grams) if grams else None)
        merged.append(a)
    return tuple(merged)


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
        "remaining_grams": slot.remaining_grams,
    }


_HINT_RANK = {HINT_FREE: 0, HINT_REPLACEABLE: 1, HINT_ALL_NEEDED: 2}


def _replace_slots(hint: SlotHint, filaments: Iterable[TodoFilament]) -> tuple[HintSlot, ...]:
    """The trays whose spools are too small for the entry, as the printer reports them (#3634).

    Looked up among the printer's loaded slots for what is in them; a tray
    that is no longer loaded is left out, and so is one that no longer holds
    the filament (a fresh spool of another one was put in). A tray that still
    fits but whose grams have gone stale is kept, with the grams it was counted
    with: a staged job's hold is not re-validated while it stays staged
    (#3615), so the next pass's hold corrects them.
    """
    loaded = {(slot.ams_id, slot.tray_id): slot for slot in hint.loaded}
    out: dict[tuple[int, int], HintSlot] = {}
    for filament in filaments:
        if not filament.short:
            continue
        for tray in filament.short_trays:
            key = (tray.ams_id, tray.tray_id)
            if key in loaded and key not in out and tray_fits_filament(loaded[key], filament):
                out[key] = replace(loaded[key], remaining_grams=tray.remaining_grams)
    return tuple(out[key] for key in sorted(out))


def settled_hint(hint: SlotHint, filaments: Iterable[TodoFilament]) -> SlotHint:
    """``hint`` for an entry's filaments: no slot that already holds a spool of one of them (#3634).

    See ``tray_fits_filament``: the matcher would use such a slot, so it is
    never offered, whether the hint is for a Load entry or a Prepare line.
    A hint that offered replaceable slots and has none left becomes
    ``all_needed``; the same goes for each nozzle's part.
    """
    filaments = tuple(filaments)

    def settle(state: str, slots: tuple[HintSlot, ...]) -> tuple[str, tuple[HintSlot, ...]]:
        kept = tuple(s for s in slots if not any(tray_fits_filament(s, f) for f in filaments))
        return (HINT_ALL_NEEDED, ()) if state == HINT_REPLACEABLE and not kept else (state, kept)

    state, slots = settle(hint.state, hint.slots)
    parts = tuple(NozzleHint(p.nozzle, *settle(p.state, p.slots)) for p in hint.by_nozzle)
    return replace(hint, state=state, slots=slots, by_nozzle=parts)


def _hint_dict(hint: SlotHint, filaments: Iterable[TodoFilament], visible_ids: Collection[int]) -> dict | None:
    """A printer's hint as one entry shows it (#3634), or None when it has nothing for the entry.

    A filament that is loaded but too little (``short``) is answered with the
    spool to replace: state ``replace`` and those trays, with what they have
    left, whatever the nozzle (and with no alternative, as the spool it needs
    is already in the printer).

    Otherwise a slot that holds a spool of one of the entry's filaments (see
    ``tray_fits_filament``) is never offered for replacing: the matcher would
    use it. When that leaves no slot, nothing is left to replace.

    On a dual-nozzle printer without a Filament Track Switch the hint has a
    part per nozzle. An entry whose filaments all name a nozzle is built from
    the parts of those nozzles alone, so it is never offered a slot of the
    other one; when none of its nozzles has a slot, there is no hint. A
    filament that names no nozzle may take any tray, as the matcher reads it,
    so such an entry shows the printer's hint over every slot.

    ``unknown_jobs`` counts only the waiting jobs in ``visible_ids``.
    """
    filaments = tuple(filaments)
    unknown_jobs = sum(1 for job_id in hint.unknown_job_ids if job_id in visible_ids)
    if replace_slots := _replace_slots(hint, filaments):
        return {
            "state": HINT_REPLACE,
            "slots": [_slot_dict(slot) for slot in replace_slots],
            "unknown_jobs": unknown_jobs,
            "by_nozzle": [],
        }

    hint = settled_hint(hint, filaments)
    state, slots, parts = hint.state, hint.slots, hint.by_nozzle
    shown: tuple[NozzleHint, ...] = ()
    if parts:
        nozzles = {f.nozzle for f in filaments}
        if None not in nozzles:
            labels = {"left" if n == 1 else "right" for n in nozzles}
            parts = tuple(p for p in parts if p.nozzle in labels)
            if not parts:
                return None
            state = min((p.state for p in parts), key=_HINT_RANK.__getitem__)
            slots = tuple(slot for p in parts if p.state == state for slot in p.slots)
            shown = parts
    return {
        "state": state,
        "slots": [_slot_dict(slot) for slot in slots],
        "unknown_jobs": unknown_jobs,
        "by_nozzle": [{"nozzle": p.nozzle, "state": p.state, "slots": [_slot_dict(x) for x in p.slots]} for p in shown],
    }


def build_todo(
    jobs: list[TodoJob],
    printers: Mapping[int, str],
    holds: Mapping[int, list[FilamentHold]],
    plate_clear_ids: Iterable[int],
    interlock: Mapping[int, str],
    power_failed_ids: Iterable[int],
    slot_hints: Mapping[int, SlotHint] | None = None,
) -> dict:
    """The response of GET /queue/todo.

    ``jobs`` are the visible pending jobs in queue order; ``printers`` maps the
    visible printer ids to their names. Printer entries need a waiting job
    that could go to that printer. ``slot_hints`` are the scheduler's, by
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
        entry = group.entries.get((kind, subkey))
        if entry is None:
            entry = group.entries[(kind, subkey)] = {"kind": kind, "jobs": [], "detail": None, "printers": [], **extra}
        else:
            # Another job waits for the same: its short trays count too (#3634).
            if "_filaments" in extra:
                entry["_filaments"] = _merge_short(entry["_filaments"], extra["_filaments"])
            for pid, fils in extra.get("_by_printer", {}).items():
                entry["_by_printer"][pid] = _merge_short(entry["_by_printer"].get(pid, fils), fils)
        if all(j["id"] != job.id for j in entry["jobs"]):
            entry["jobs"].append(
                {"id": job.id, "name": job.name, "can_start": kind == KIND_START_STAGED and job.can_start}
            )

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
                own: dict[tuple, dict[int, tuple[TodoFilament, ...]]] = {}
                for hold in visible:
                    if len(hold.filaments) == fewest:
                        sets = by_set.setdefault(_fil_key(hold.filaments), (_sorted(hold.filaments), set()))
                        assert hold.printer_id is not None
                        sets[1].add(hold.printer_id)
                        # A short spool is a tray of that printer.
                        own.setdefault(_fil_key(hold.filaments), {})[hold.printer_id] = _sorted(hold.filaments)
                for key, (fils, ids) in by_set.items():
                    add(
                        group_for(None, job.model_key, job.model_label, index),
                        KIND_LOAD_FILAMENT,
                        (key, tuple(sorted(ids))),
                        job,
                        _filaments=fils,
                        _by_printer=own[key],
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
                by_printer = entry.pop("_by_printer", {})
                # The trays of a short spool are named for a printer: an entry
                # for an "Any <model>" group says "short", its printers' hints
                # say where.
                entry["filaments"] = [
                    {
                        "type": f.type,
                        "color": f.color,
                        "color_name": f.color_name,
                        "no_stock": f.no_stock,
                        "nozzle": f.nozzle,
                        "short": f.short,
                        "short_trays": []
                        if group.printer_id is None
                        else [
                            {"ams_id": t.ams_id, "tray_id": t.tray_id, "remaining_grams": t.remaining_grams}
                            for t in f.short_trays
                        ],
                        "required_grams": f.required_grams,
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
                            and (shown := _hint_dict(slot_hints[p["id"]], by_printer.get(p["id"], fils), index_of))
                            is not None
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
