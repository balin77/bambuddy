"""The queue's "To do" list: what each waiting job needs a person for (#3615).

Two sources, neither parsed from ``waiting_reason`` text: the printers' live
state (plate to clear, sensor interlock, failed power-on) and the jobs' own
state (staged for a manual start, plus the structured filament holds the
scheduler records next to the words it writes). This module holds the shared
records and the pure part of the list; the route gathers the inputs.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Collection, Iterable, Mapping
from dataclasses import dataclass, field, replace

from backend.app.utils.color_utils import colors_are_similar
from backend.app.utils.filament_types import canonical_filament_type
from backend.app.utils.tray_ids import TrayLayout, external_slot_index, is_ams_ht_id

KIND_PRINT_PAUSED = "print_paused"
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
# A spool the job needs holds too little: that spool is the one to replace.
HINT_REPLACE = "replace"

# Order of the entries inside one group.
_KIND_ORDER = (
    KIND_PRINT_PAUSED,
    KIND_PLATE_CLEAR,
    KIND_PLATE_CHANGER_EMPTY,
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
    # Only on a slot of a "replace" hint: what the spool has left, when known.
    remaining_grams: float | None = None


@dataclass(frozen=True)
class PictureSlot:
    """One slot of a printer as the AMS picture draws it (#3726): every slot, loaded or not.

    ``ams_id`` / ``tray_id`` are the keys the inventory stores a slot under
    (the external holder is unit 255, its slot 0 or 1), so the picture's
    buttons act on the same slot the printer card does. ``extruder`` is the
    nozzle the unit feeds on a dual-nozzle printer (0 right, 1 left).
    ``empty`` is a slot the printer confirms holds no spool; a slot with
    neither a filament nor that confirmation is ``unknown`` (a spool the
    printer cannot identify). ``remain`` is the printer's own percentage, -1
    or None when it reports none.
    """

    ams_id: int
    tray_id: int
    global_tray_id: int
    is_ht: bool
    is_external: bool
    ams_type: int | None
    extruder: int | None
    type: str = ""
    color: str = ""
    tray_info_idx: str = ""
    tray_sub_brands: str = ""
    # RRGGBBAA of a translucent or clear spool (alpha below FF); empty otherwise.
    rgba: str = ""
    empty: bool = False
    rfid: bool = False
    remain: int | None = None

    @property
    def key(self) -> tuple[int, int]:
        return (self.ams_id, self.tray_id)

    @property
    def loaded(self) -> bool:
        return bool(self.type)

    def as_hint_slot(self) -> HintSlot:
        return HintSlot(
            self.ams_id, self.tray_id, self.is_ht, self.is_external, self.ams_type, None,
            self.type, self.color, self.tray_info_idx, self.tray_sub_brands,
        )  # fmt: skip


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
    # What the AMS picture is drawn from (#3726): every slot of the printer at
    # the time of the pass, the trays waiting jobs or the running print use,
    # the running print's own trays, and whether a filament that names a
    # nozzle may only go to that nozzle's slots. Nothing a decision reads, and
    # none of it takes part in equality, so hints compare as they did before.
    picture: tuple[PictureSlot, ...] = field(default=(), compare=False)
    needed: frozenset[int] = field(default=frozenset(), compare=False)
    running: frozenset[int] = field(default=frozenset(), compare=False)
    nozzle_split: bool = field(default=False, compare=False)

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


def merge_todo_filaments(into: list[TodoFilament], more: Iterable[TodoFilament]) -> None:
    """Add the filaments of ``more`` that ``into`` lacks, in place.

    ``forced`` and ``tray_info_idx`` are not compared, so a filament already
    there stands for its twin; the forced twin wins (the flag is OR-ed), or the
    stock flag of the forced one would be lost (#3615). A repeat is the same
    filament on the same short trays; a short spool and a missing one of the
    same filament stay two (#3634).
    """
    for f in more:
        for i, known in enumerate(into):
            if known == f and _identity(known) == _identity(f):
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


def tray_fits_filament(slot: HintSlot, filament: TodoFilament) -> bool:
    """Whether a loaded tray is a spool of ``filament``, as the dispatch matcher reads it (#3634).

    The same canonical type, and a colour that is the same (exact when the
    filament forces the colour match) or similar (the matcher's per-channel
    threshold); and when both sides name a filament preset (``tray_info_idx``),
    the same one. A tray that fits is not offered as a place to load that
    filament: the matcher would use it. See ``_match_filaments_to_slots`` and
    ``_missing_force_color_pairs``, which a test holds this against.

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
    # Whether the caller may start it now (only read for a staged job, or a job
    # that waits only for a short spool, #3659).
    can_start: bool = False
    # Whether Start can bind a model job to one of its printers. Not a job with
    # printer alternatives (#671): its printer is chosen with its file.
    pinnable: bool = True


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
    prepare: list[dict] = field(default_factory=list)


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


def _paused_slot_dict(slot: PausedSlot | None) -> dict | None:
    return None if slot is None else {f: getattr(slot, f) for f in PausedSlot.__dataclass_fields__}


def _paused_dict(info: PausedInfo) -> dict:
    cause = info.cause
    return {
        "job_name": info.job_name,
        "progress": info.progress,
        "remaining_minutes": info.remaining_minutes,
        "cause": cause.cause,
        "ran_out": _paused_slot_dict(cause.ran_out),
        "expected": _paused_slot_dict(cause.expected),
        "error": (
            {"code": cause.error_code, "description": cause.error_description} if cause.cause == CAUSE_ERROR else None
        ),
        "more_errors": cause.more_errors,
    }


def _waits_only_for_short_spool(job: TodoJob, holds: Iterable[FilamentHold]) -> bool:
    """Whether a waiting (not staged) job is held only because spools are short (#3659).

    Every filament of every hold is loaded but too little of it. A job that
    misses a filament altogether, on any printer, has no "Print anyway".
    """
    if job.manual_start:
        return False
    filaments = [f for hold in holds for f in hold.filaments]
    return bool(filaments) and all(f.short for f in filaments)


def _short_only_printers(job: TodoJob, holds: Iterable[FilamentHold]) -> set[int]:
    """The printers on which a waiting (not staged) job is held only because spools are short.

    Judged per printer, unlike ``_waits_only_for_short_spool``: an "Any
    <model>" job can have every filament loaded (too little of it) on one
    printer and lack one on another. On the first it can be started anyway,
    whatever the others lack. Only printers the job could go to count, and a
    model job only when Start can bind it to one (``TodoJob.pinnable``).
    """
    if job.manual_start or (job.pinned_id is None and not job.pinnable):
        return set()
    by_printer: dict[int, list[TodoFilament]] = {}
    for hold in holds:
        if hold.printer_id is not None:
            by_printer.setdefault(hold.printer_id, []).extend(hold.filaments)
    return {
        printer_id
        for printer_id, filaments in by_printer.items()
        if printer_id in job.printer_ids and filaments and all(f.short for f in filaments)
    }


# States of a slot in the AMS picture (#3726).
PICTURE_KEEP = "keep"
PICTURE_OUT = "out"
PICTURE_EMPTY = "empty"
PICTURE_FITS = "fits"
PICTURE_LOCKED = "locked"
PICTURE_UNKNOWN = "unknown"

# AmsType values (utils/tray_ids) by what the picture calls the unit.
_KIND_AMS_LITE = {2, 5}
_KIND_HT = {4}
_KIND_AMS3H = {6, 7}


@dataclass(frozen=True)
class SlotExtra:
    """What the inventory knows of the spool assigned to a slot (#3726): grams left and how it looks."""

    remaining_grams: float | None = None
    extra_colors: str = ""
    effect_type: str = ""
    subtype: str = ""
    color_name: str = ""


def _unit_kind(slot: PictureSlot) -> str:
    if slot.is_external:
        return "external"
    if slot.is_ht or slot.ams_type in _KIND_HT:
        return "ht"
    if slot.ams_type in _KIND_AMS3H:
        return "ams3h"
    if slot.ams_type in _KIND_AMS_LITE:
        return "ams_lite"
    return "ams"


def _find_slot(slots: Iterable[PictureSlot], ams_id: int, tray_id: int) -> PictureSlot | None:
    """The slot a short tray names; the external holder is told by any of its ids (-1, 254, 255)."""
    external = ams_id in (-1, 254, 255)
    for slot in slots:
        if slot.tray_id == tray_id and (slot.is_external if external else slot.ams_id == ams_id):
            return slot
    return None


def place_filaments(
    hint: SlotHint, filaments: tuple[TodoFilament, ...]
) -> tuple[dict[tuple[int, int], int], set[tuple[int, int]], list[int]]:
    """Where an entry's filaments go on the picture of ``hint`` (#3726): a reading of the scheduler's own hint, no new decision.

    Returns the slot of each incoming filament (slot key to filament index),
    the slots whose spool goes out, and the filaments with no slot. A short
    filament goes to its own tray (the first of them, when pooled) and every
    one of its trays goes out. A missing one takes the first empty slot the
    hint offers, else a loaded slot no waiting job and no running print uses
    and no filament of the entry fits (``_classify_slots``, ``_claimed_trays``
    in the scheduler), on its nozzle when it names one and the printer feeds
    by nozzle. A slot of the running print is never taken.
    """
    slots = hint.picture
    locked = hint.running
    needed = hint.needed | locked
    incoming: dict[tuple[int, int], int] = {}
    out: set[tuple[int, int]] = set()
    unplaced: list[int] = []
    for index, filament in enumerate(filaments):
        if not filament.short:
            continue
        # A tray of the running print is locked, never taken out: the filament has no slot.
        found = [
            s
            for t in filament.short_trays
            if (s := _find_slot(slots, t.ams_id, t.tray_id)) is not None and s.global_tray_id not in locked
        ]
        if not found or found[0].key in incoming:
            unplaced.append(index)
            continue
        out.update(s.key for s in found)
        incoming[found[0].key] = index

    def order(slot: PictureSlot) -> tuple[bool, int, int]:
        return (slot.is_external, slot.ams_id, slot.tray_id)

    for index, filament in enumerate(filaments):
        if filament.short:
            continue
        scope = slots
        if hint.nozzle_split and filament.nozzle in (0, 1):
            scope = tuple(s for s in slots if s.extruder == filament.nozzle)
        # As ``_classify_slots``: the external holder is only offered when the
        # printer has no AMS slot at all, locked or taken or not.
        has_ams = any(not s.is_external for s in scope)
        pool = [s for s in scope if s.key not in incoming and s.global_tray_id not in locked]
        free = [s for s in pool if s.empty and not (s.is_external and has_ams) and s.global_tray_id not in needed]
        replaceable = [
            s
            for s in pool
            if s.loaded
            and s.global_tray_id not in needed
            and not (s.is_external and has_ams)
            and not any(tray_fits_filament(s.as_hint_slot(), f) for f in filaments)
        ]
        chosen = (sorted(free, key=order) + sorted(replaceable, key=order))[:1]
        if not chosen:
            unplaced.append(index)
            continue
        incoming[chosen[0].key] = index
        if chosen[0].loaded:
            out.add(chosen[0].key)
    return incoming, out, unplaced


def picture_dict(
    hint: SlotHint | None,
    printer_id: int,
    printer_name: str,
    filaments: Iterable[TodoFilament],
    extras: Mapping[tuple[int, int, int], SlotExtra] | None = None,
    stock_for: Callable[[TodoFilament], int | None] | None = None,
    compact: bool = False,
) -> dict | None:
    """The AMS picture of one printer for an entry (#3726), or None when the printer reported no slots.

    One unit per AMS (each AMS-HT its own, the external holder last), every
    slot with its state, the incoming filaments on the slot they go to. Units
    that receive something are open; the others are ``collapsed`` (the page
    folds them behind a toggle). With nothing placed the first unit is open,
    so the picture is never empty. ``extras`` (by printer, unit, slot) bring the
    grams and looks of the assigned spool; a short filament's own grams are
    used for its trays when there are none. ``stock_for`` counts the spools in
    stock for an incoming filament; left out in a compact picture.
    """
    if hint is None or not hint.picture:
        return None
    filaments = tuple(filaments)
    extras = extras or {}
    incoming, out, unplaced = place_filaments(hint, filaments)
    short_grams = {
        (t.ams_id, t.tray_id): t.remaining_grams for f in filaments if f.short for t in f.short_trays
    }  # fmt: skip

    def state_of(slot: PictureSlot) -> str:
        if slot.key in out:
            return PICTURE_OUT
        if slot.key in incoming and not slot.loaded:
            return PICTURE_EMPTY
        if slot.global_tray_id in hint.running:
            return PICTURE_LOCKED
        if not slot.loaded:
            return PICTURE_EMPTY if slot.empty or slot.is_external else PICTURE_UNKNOWN
        if any(tray_fits_filament(slot.as_hint_slot(), f) for f in filaments if not f.short):
            return PICTURE_FITS
        return PICTURE_KEEP

    def slot_dict(slot: PictureSlot) -> dict:
        extra = extras.get((printer_id, slot.ams_id, slot.tray_id)) or SlotExtra()
        grams = extra.remaining_grams
        if grams is None:
            grams = short_grams.get(slot.key)
        index = incoming.get(slot.key)
        filament = filaments[index] if index is not None else None
        return {
            "ams_id": slot.ams_id,
            "tray_id": slot.tray_id,
            "is_ht": slot.is_ht,
            "is_external": slot.is_external,
            "ams_type": slot.ams_type,
            "type": slot.type,
            "color": slot.color,
            "rgba": slot.rgba,
            "extra_colors": extra.extra_colors,
            "effect_type": extra.effect_type,
            "subtype": extra.subtype,
            "color_name": extra.color_name,
            "tray_sub_brands": slot.tray_sub_brands,
            "tray_info_idx": slot.tray_info_idx,
            "remaining_g": grams,
            "remain_percent": slot.remain if slot.remain is not None and slot.remain >= 0 else None,
            "rfid": slot.rfid,
            "state": state_of(slot),
            "incoming": None
            if filament is None
            else {
                "filament_index": index,
                "type": filament.type,
                "color": filament.color,
                "color_name": filament.color_name,
                "required_g": filament.required_grams,
                "stock_count": None if compact or stock_for is None else stock_for(filament),
            },
        }

    grouped: dict[tuple[bool, int, int], list[PictureSlot]] = {}
    for slot in sorted(hint.picture, key=lambda s: (s.is_external, s.ams_id, s.tray_id)):
        # On a two-nozzle printer each external holder feeds its own nozzle: a unit of its own.
        split_external = slot.is_external and slot.extruder is not None
        grouped.setdefault((slot.is_external, slot.ams_id, slot.tray_id if split_external else -1), []).append(slot)
    units = []
    for unit_slots in grouped.values():
        first = unit_slots[0]
        units.append(
            {
                "ams_id": first.ams_id,
                "ams_type": first.ams_type,
                "kind": _unit_kind(first),
                "nozzle": None if first.extruder is None else ("left" if first.extruder == 1 else "right"),
                "slots": [slot_dict(s) for s in unit_slots],
            }
        )
    involved = [u for u in units if any(s["incoming"] or s["state"] == PICTURE_OUT for s in u["slots"])]
    shown = involved or units[:1]
    for unit in units:
        unit["collapsed"] = unit not in shown
    return {
        "printer_id": printer_id,
        "printer_name": printer_name,
        "compact": compact,
        "units": units,
        "unplaced": unplaced,
    }


def _filament_dicts(filaments: Iterable[TodoFilament], trays: bool) -> list[dict]:
    """The filaments as the response lists them; ``trays`` False leaves the short trays out."""
    return [
        {
            "type": f.type,
            "color": f.color,
            "color_name": f.color_name,
            "no_stock": f.no_stock,
            "nozzle": f.nozzle,
            "short": f.short,
            "short_trays": [
                {"ams_id": t.ams_id, "tray_id": t.tray_id, "remaining_grams": t.remaining_grams} for t in f.short_trays
            ]
            if trays
            else [],
            "required_grams": f.required_grams,
        }
        for f in filaments
    ]


def _outs(picture: dict) -> int:
    return sum(1 for u in picture["units"] for s in u["slots"] if s["state"] == PICTURE_OUT)


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
    prepare: Mapping[int, Iterable[PrepareEntry]] | None = None,
    slot_extras: Mapping[tuple[int, int, int], SlotExtra] | None = None,
    stock_for: Callable[[TodoFilament], int | None] | None = None,
    idle_printers: Collection[int] = (),
    *,
    paused: Mapping[int, PausedInfo] | None = None,
) -> dict:
    """The response of GET /queue/todo.

    ``jobs`` are the visible pending jobs in queue order; ``printers`` maps the
    visible printer ids to their names. Printer entries need a waiting job
    that could go to that printer. ``plate_changer_empty`` maps the printers
    whose plate changer has no plate left to their capacity (#3575);
    ``priorities`` maps a job to its place in the loaded-filament-first wait
    (#3587). ``slot_hints`` are the scheduler's, by
    printer id: a load entry carries its printer's (a model entry one per
    printer it lists), and never names a job (#3634). ``prepare`` are the
    scheduler's lines for a printer's next jobs, by printer id: shown under
    the printer, for the jobs and printers in ``jobs`` and ``printers`` only,
    and not counted (#3640). Their positions are renumbered for what the
    caller sees, so the first visible line is always position 1. A group with
    neither entries nor lines is left out. A paused print is listed whether or
    not a job waits (#3648); ``paused`` maps a printer id to it.

    Each job of a load entry names the entry's printers on which it is held
    only because spools are short (``short_only_printer_ids``): "Print anyway"
    is offered for those, per printer.

    A load entry also carries the AMS picture of its printer, ``ams_picture``
    (a model entry ``ams_pictures``, one per listed printer, the one that
    would likely take the job first, an idle one with the fewest spools to
    take out, at the front), and a prepare line a compact one (#3726). A
    model entry lists the printers that miss the fewest filaments, among the
    idle ones when any is idle; the job's other printers with a hold follow in
    ``ams_pictures``, and every picture there has its own ``filaments``. They
    are drawn from the same hints; ``slot_extras`` bring the inventory's grams
    and looks, ``stock_for`` the spools in stock, ``idle_printers`` the
    printers that are connected and not printing. None of them changes an
    entry, the count or a hint.
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
            entry = group.entries[(kind, subkey)] = {
                "kind": kind,
                "jobs": [],
                "detail": None,
                "printers": [],
                "priority": None,
                "priority_hours": None,
                "plate_capacity": None,
                **extra,
            }
        else:
            # Another job waits for the same: its short trays count too (#3634).
            if "_filaments" in extra:
                entry["_filaments"] = _merge_short(entry["_filaments"], extra["_filaments"])
            for pid, fils in extra.get("_by_printer", {}).items():
                entry["_by_printer"][pid] = _merge_short(entry["_by_printer"].get(pid, fils), fils)
            # What the entry's jobs miss on a printer it does not list, together.
            for pid, fils in extra.get("_others", {}).items():
                merge_todo_filaments(entry["_others"].setdefault(pid, []), fils)
        if kind == KIND_LOAD_FILAMENT and priorities and job.id in priorities:
            state = priorities[job.id]
            if _more_urgent(state, (entry["priority"], entry["priority_hours"]) if entry["priority"] else None):
                entry["priority"], entry["priority_hours"] = state
        if all(j["id"] != job.id for j in entry["jobs"]):
            # A job that waits only for a short spool can be started anyway (#3659).
            short_only = kind == KIND_LOAD_FILAMENT and _waits_only_for_short_spool(job, holds.get(job.id, []))
            # Per printer of the entry: a model job is offered where it is
            # short, whatever its other printers lack.
            short_on: list[int] = []
            if kind == KIND_LOAD_FILAMENT:
                shown = [group.printer_id] if group.printer_id is not None else [p["id"] for p in entry["printers"]]
                short_ids = _short_only_printers(job, holds.get(job.id, []))
                short_on = sorted(pid for pid in shown if pid in short_ids or (short_only and pid == job.pinned_id))
            entry["jobs"].append(
                {
                    "id": job.id,
                    "name": job.name,
                    "can_start": (kind == KIND_START_STAGED or short_only or bool(short_on)) and job.can_start,
                    "short_only": short_only,
                    "short_only_printer_ids": short_on,
                }
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
            # that miss the fewest filaments are where loading them lets it
            # start. A printer that is idle can take it now, so when one is
            # idle only the idle ones are counted; the job's other printers
            # (printing, or missing more) are reached through the entry's
            # picture switch, each with its own filaments.
            visible = [h for h in holds_of_job if h.printer_id in printers]
            if visible:
                pool = [h for h in visible if h.printer_id in idle_printers] or visible
                fewest = min(len(h.filaments) for h in pool)
                by_set: dict[tuple, tuple[tuple[TodoFilament, ...], set[int]]] = {}
                own: dict[tuple, dict[int, tuple[TodoFilament, ...]]] = {}
                others: dict[int, list[TodoFilament]] = {}
                for hold in visible:
                    assert hold.printer_id is not None
                    if hold in pool and len(hold.filaments) == fewest:
                        sets = by_set.setdefault(_fil_key(hold.filaments), (_sorted(hold.filaments), set()))
                        sets[1].add(hold.printer_id)
                        # A short spool is a tray of that printer.
                        own.setdefault(_fil_key(hold.filaments), {})[hold.printer_id] = _sorted(hold.filaments)
                    else:
                        merge_todo_filaments(others.setdefault(hold.printer_id, []), hold.filaments)
                listed = {pid for _fils, ids in by_set.values() for pid in ids}
                for key, (fils, ids) in by_set.items():
                    add(
                        group_for(None, job.model_key, job.model_label, index),
                        KIND_LOAD_FILAMENT,
                        (key, tuple(sorted(ids))),
                        job,
                        _filaments=fils,
                        _by_printer=own[key],
                        _others={pid: list(more) for pid, more in others.items() if pid not in listed},
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

    # Prepare lines: a job the caller may not see is no line. A printer with
    # nothing else to do gets a group of its own.
    jobs_by_id = {job.id: job for job in jobs}
    for printer_id, lines in (prepare or {}).items():
        if printer_id not in printers:
            continue
        for line in lines:
            job = jobs_by_id.get(line.item_id)
            if job is None:
                continue
            group_for(printer_id, None, None, index_of[job.id]).prepare.append(
                {
                    "job": {"id": job.id, "name": job.name},
                    "position": line.position,
                    "filaments": [
                        {
                            "type": f.type,
                            "color": f.color,
                            "color_name": f.color_name,
                            "no_stock": f.no_stock,
                            "nozzle": f.nozzle,
                            # A Prepare line lists what is missing, never a short spool.
                            "short": False,
                            "short_trays": [],
                            "required_grams": None,
                        }
                        for f in _sorted(line.filaments)
                    ],
                    "slot_hint": _hint_dict(line.hint, line.filaments, index_of) if line.hint else None,
                    "ams_picture": picture_dict(
                        line.hint, printer_id, printers[printer_id], _sorted(line.filaments), slot_extras, compact=True
                    ),
                }
            )

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
                others = {pid: _sorted(more) for pid, more in entry.pop("_others", {}).items()}
                # The trays of a short spool are named for a printer: an entry
                # for an "Any <model>" group says "short", its printers' hints
                # say where.
                entry["filaments"] = _filament_dicts(fils, trays=group.printer_id is not None)
                if kind == KIND_LOAD_FILAMENT:
                    if group.printer_id is not None:
                        hint = slot_hints.get(group.printer_id)
                        entry["slot_hint"] = _hint_dict(hint, fils, index_of) if hint else None
                        entry["ams_picture"] = picture_dict(
                            hint, group.printer_id, group.printer_name, fils, slot_extras, stock_for
                        )
                    else:
                        entry["slot_hints"] = [
                            {"printer_id": p["id"], **shown}
                            for p in entry["printers"]
                            if p["id"] in slot_hints
                            and (shown := _hint_dict(slot_hints[p["id"]], by_printer.get(p["id"], fils), index_of))
                            is not None
                        ]
                        # One picture per printer the job could go to: the
                        # ones the entry lists, then the job's other printers.
                        # Each carries the filaments it is drawn for, as the
                        # others miss a different set.
                        candidates = [(p["id"], p["name"], by_printer.get(p["id"], fils)) for p in entry["printers"]]
                        candidates += [(pid, printers[pid], more) for pid, more in others.items()]
                        pictures = []
                        for pid, name, own_fils in candidates:
                            picture = picture_dict(slot_hints.get(pid), pid, name, own_fils, slot_extras, stock_for)
                            if picture is not None:
                                picture["filaments"] = _filament_dicts(own_fils, trays=False)
                                pictures.append(picture)
                        # The printer that would likely take the job first: idle
                        # and connected, a listed one before another, with the
                        # fewest spools to take out.
                        pictures.sort(
                            key=lambda pic: (
                                pic["printer_id"] not in idle_printers,
                                pic["printer_id"] in others,
                                _outs(pic),
                                pic["printer_id"],
                            )
                        )
                        entry["ams_pictures"] = pictures
                entries.append(entry)
        # What the caller sees of a printer's lines is numbered again: when the
        # nearest job is not theirs, the first line they see is the next one.
        lines = sorted(group.prepare, key=lambda line: line["position"])
        for position, line in enumerate(lines, start=1):
            line["position"] = position
        if not entries and not lines:
            continue
        count += len(entries)
        out_groups.append(
            {
                "printer_id": group.printer_id,
                "printer_name": group.printer_name,
                "target_model": group.target_model,
                "entries": entries,
                "prepare": lines,
            }
        )
    return {"count": count, "groups": out_groups}
