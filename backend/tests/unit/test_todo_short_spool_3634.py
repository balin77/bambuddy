"""The To do list says when a spool has too little filament and which one to replace (#3634)."""

import json
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.app.services.filament_deficit import FilamentDeficit, compute_deficit_for_queue_item, describe_deficit
from backend.app.services.print_scheduler import PrintScheduler
from backend.app.services.queue_todo import (
    HINT_ALL_NEEDED,
    HINT_REPLACE,
    HINT_REPLACEABLE,
    FilamentHold,
    HintSlot,
    NozzleHint,
    ShortTray,
    SlotHint,
    TodoFilament,
    TodoJob,
    _hint_dict,
    _merge_short,
    build_todo,
    todo_filament_from_requirement,
    tray_fits_filament,
    unique_filaments,
)
from backend.tests.unit.services.test_filament_deficit import (
    TestFilamentDeficitBackupAware,
    _assign,
    _queue_item,
    _setup_archive_3mf,
    _spool,
)
from backend.tests.unit.test_slot_hints_3634 import (
    GREEN,
    RED,
    WHITE,
    _dual,
    _hints,
    _holds,
    _job,
    _loaded_ams,
    _need,
    _scheduler_with,
    _status,
    _tray,
)

LAVA = "#C12E1F"
BEIGE = "#A89F8B"
COTTON = "#F5F5F0"


def _slot(ams_id, tray_id, material="PLA", color="", idx="", nozzle=None):
    return HintSlot(ams_id, tray_id, False, False, 1, nozzle, material, color, idx)


# The farm: A1 + AMS Lite, A1 Army Beige, A2 and A3 Lava Red, A4 Cotton White.
FARM = (
    _slot(0, 0, color=BEIGE),
    _slot(0, 1, color=LAVA),
    _slot(0, 2, color=LAVA),
    _slot(0, 3, color=COTTON),
)


def _farm_hint(state=HINT_REPLACEABLE, slots=None, **fields):
    return SlotHint(1, state, FARM if slots is None else slots, loaded=FARM, **fields)


def _short(trays, required=30.0, **fields):
    return TodoFilament(
        "PLA", LAVA, "Lava Red", short=True, short_trays=tuple(trays), required_grams=required, **fields
    )


def _ids(shown):
    return [(s["ams_id"], s["tray_id"]) for s in shown["slots"]]


class TestShortSpoolHint:
    def test_the_farm_case_names_the_short_spool_and_nothing_else(self):
        shown = _hint_dict(_farm_hint(), (_short([ShortTray(0, 1, 12.0)]),), {})
        assert shown["state"] == HINT_REPLACE
        assert _ids(shown) == [(0, 1)]
        assert shown["slots"][0]["remaining_grams"] == 12.0
        assert (shown["slots"][0]["type"], shown["slots"][0]["color"]) == ("PLA", LAVA)
        assert shown["by_nozzle"] == []

    def test_a_pooled_spool_is_named_too(self):
        trays = [ShortTray(0, 1, 12.0), ShortTray(0, 2, 13.0)]
        shown = _hint_dict(_farm_hint(), (_short(trays),), {})
        assert shown["state"] == HINT_REPLACE
        assert _ids(shown) == [(0, 1), (0, 2)]

    def test_unknown_grams_are_null(self):
        shown = _hint_dict(_farm_hint(), (_short([ShortTray(0, 1, None)], required=None),), {})
        assert shown["slots"][0]["remaining_grams"] is None

    def test_a_tray_now_holding_another_filament_is_not_named(self):
        # A2 was swapped for a fresh PETG spool since the hold was written.
        swapped = (FARM[0], _slot(0, 1, "PETG", "#000000"), *FARM[2:])
        hint = SlotHint(1, HINT_REPLACEABLE, swapped, loaded=swapped)
        shown = _hint_dict(hint, (_short([ShortTray(0, 1, 12.0)]),), {})
        assert shown["state"] != HINT_REPLACE
        # The normal hint: the tray of the new spool is a place to load.
        assert (0, 1) in _ids(shown)

    def test_only_the_swapped_tray_of_a_pool_is_dropped(self):
        swapped = (FARM[0], FARM[1], _slot(0, 2, "PETG", "#000000"), FARM[3])
        hint = SlotHint(1, HINT_REPLACEABLE, swapped, loaded=swapped)
        trays = [ShortTray(0, 1, 12.0), ShortTray(0, 2, 13.0)]
        shown = _hint_dict(hint, (_short(trays),), {})
        assert shown["state"] == HINT_REPLACE
        assert _ids(shown) == [(0, 1)]

    def test_a_tray_that_still_fits_keeps_its_counted_grams(self):
        shown = _hint_dict(_farm_hint(), (_short([ShortTray(0, 1, 12.0)]),), {})
        assert shown["slots"][0]["remaining_grams"] == 12.0

    def test_a_tray_that_is_no_longer_loaded_is_not_named(self):
        hint = SlotHint(1, HINT_REPLACEABLE, FARM[:1], loaded=FARM[:1])
        shown = _hint_dict(hint, (_short([ShortTray(0, 1, 12.0)]),), {})
        assert shown["state"] != HINT_REPLACE

    def test_replace_is_named_when_the_hint_has_no_part_for_the_nozzle(self):
        # Only the left nozzle has a slot; the short filament is on the right.
        left = _slot(1, 0, color=BEIGE, nozzle="left")
        right = _slot(0, 1, color=LAVA, nozzle="right")
        hint = SlotHint(
            1,
            HINT_REPLACEABLE,
            (left,),
            by_nozzle=(NozzleHint("left", HINT_REPLACEABLE, (left,)),),
            loaded=(left, right),
        )
        fil = _short([ShortTray(0, 1, 5.0)], nozzle=0)
        assert _hint_dict(hint, (fil,), {})["state"] == HINT_REPLACE
        # A missing filament on that nozzle still gets no hint.
        assert _hint_dict(hint, (replace(fil, short=False, short_trays=()),), {}) is None

    def test_each_part_of_a_dual_nozzle_hint_is_filtered_for_a_missing_filament(self):
        left = _slot(1, 0, color=LAVA, nozzle="left")
        left2 = _slot(1, 1, color=BEIGE, nozzle="left")
        right = _slot(0, 1, color=LAVA, nozzle="right")
        hint = SlotHint(
            1,
            HINT_REPLACEABLE,
            (left, left2, right),
            by_nozzle=(
                NozzleHint("right", HINT_REPLACEABLE, (right,)),
                NozzleHint("left", HINT_REPLACEABLE, (left, left2)),
            ),
            loaded=(left, left2, right),
        )
        missing = TodoFilament("PLA", LAVA, "Lava Red", nozzle=1)
        shown = _hint_dict(hint, (missing,), {})
        assert _ids(shown) == [(1, 1)]
        assert shown["by_nozzle"] == [
            {"nozzle": "left", "state": HINT_REPLACEABLE, "slots": [shown["slots"][0]]},
        ]
        # Nothing but the spool of that very filament on the right nozzle: nothing to replace there.
        on_right = _hint_dict(hint, (replace(missing, nozzle=0),), {})
        assert (on_right["state"], on_right["slots"]) == (HINT_ALL_NEEDED, [])


class TestMissingFilamentNeverOffersItsOwnColour:
    def test_a_slot_with_the_same_filament_is_not_offered(self):
        missing = TodoFilament("PLA", LAVA, "Lava Red")
        shown = _hint_dict(_farm_hint(), (missing,), {})
        assert _ids(shown) == [(0, 0), (0, 3)]

    def test_everything_offered_being_the_filament_leaves_all_needed(self):
        hint = SlotHint(1, HINT_REPLACEABLE, FARM[1:3], loaded=FARM)
        shown = _hint_dict(hint, (TodoFilament("PLA", LAVA, "Lava Red"),), {})
        assert (shown["state"], shown["slots"]) == (HINT_ALL_NEEDED, [])

    def test_a_similar_colour_is_not_offered(self):
        near = _slot(0, 4, color="#C73023")
        hint = SlotHint(1, HINT_REPLACEABLE, (near, FARM[0]), loaded=(near, FARM[0]))
        assert _ids(_hint_dict(hint, (TodoFilament("PLA", LAVA, "Lava Red"),), {})) == [(0, 0)]

    def test_a_forced_colour_is_exact_only(self):
        near = _slot(0, 4, color="#C73023")
        hint = SlotHint(1, HINT_REPLACEABLE, (near, FARM[1]), loaded=(near, FARM[1]))
        forced = TodoFilament("PLA", LAVA, "Lava Red", forced=True)
        assert _ids(_hint_dict(hint, (forced,), {})) == [(0, 4)]

    def test_a_forced_colour_no_eye_tells_apart_is_not_offered(self):
        # The scheduler takes 55B687 for a forced 55B688 (#3763), so the list must not offer it.
        twin = _slot(0, 4, color="#55B687")
        hint = SlotHint(1, HINT_REPLACEABLE, (twin, FARM[1]), loaded=(twin, FARM[1]))
        forced = TodoFilament("PLA", "#55B688", "Mint", forced=True)
        assert _ids(_hint_dict(hint, (forced,), {})) == [(0, 1)]

    def test_a_different_preset_is_still_offered(self):
        matte = _slot(0, 1, color=LAVA, idx="GFA01")
        hint = SlotHint(1, HINT_REPLACEABLE, (matte,), loaded=(matte,))
        missing = TodoFilament("PLA", LAVA, "Lava Red", tray_info_idx="GFA00")
        assert _ids(_hint_dict(hint, (missing,), {})) == [(0, 1)]
        # Without a preset on either side the colour decides.
        assert _hint_dict(hint, (TodoFilament("PLA", LAVA, "Lava Red"),), {})["state"] == HINT_ALL_NEEDED

    def test_another_type_is_offered(self):
        petg = _slot(0, 1, "PETG", LAVA)
        hint = SlotHint(1, HINT_REPLACEABLE, (petg,), loaded=(petg,))
        assert _ids(_hint_dict(hint, (TodoFilament("PLA", LAVA, "Lava Red"),), {})) == [(0, 1)]


class TestPredicateAgreesWithTheMatcher:
    """``tray_fits_filament`` is the matcher's own reading of "this tray is that filament".

    The check runs one way on purpose: a tray the predicate calls fitting must
    be one the matcher takes (or, forced, finds). The converse does not hold:
    the predicate is stricter than the matcher, which also takes a tray the
    list still offers (a different type through a fallback, the other nozzle's
    tray), and offering a tray the matcher might use is the lesser harm.
    """

    CASES = [
        # (filament type, colour, idx, forced), (tray type, colour, idx)
        (("PLA", "#C12E1F", "", False), ("PLA", "#C12E1F", "")),
        (("PLA", "#C12E1F", "", False), ("PLA", "#C73023", "")),
        (("PLA", "#C12E1F", "", True), ("PLA", "#C73023", "")),
        (("PLA", "#C12E1F", "GFA00", True), ("PLA", "#C12E1F", "GFA01")),
        (("PLA", "#C12E1F", "GFA00", True), ("PLA", "#C12E1F", "")),
        (("PLA", "#C12E1F", "", True), ("PLA", "#C12E1F", "GFA01")),
        (("PLA", "#C12E1F", "", False), ("PETG", "#C12E1F", "")),
        (("PLA-CF", "#C12E1F", "", False), ("PLA-CF", "#C12E1F", "")),
        (("PLA", "#C12E1F", "", True), ("PLA", "#00FF00", "")),
        # A shade of rounding no eye tells apart counts as the forced colour (#3763).
        (("PLA", "#55B688", "", True), ("PLA", "#55B687", "")),
    ]

    @staticmethod
    def _raw(tray):
        return {
            "ams": [
                {"id": 0, "tray": [{"tray_type": tray[0], "tray_color": tray[1][1:] + "FF", "tray_info_idx": tray[2]}]}
            ]
        }

    @pytest.mark.parametrize(("fil", "tray"), CASES)
    def test_forced_filaments_fit_exactly_when_the_matcher_finds_them(self, fil, tray):
        scheduler = PrintScheduler()
        override = {"type": fil[0], "color": fil[1], "tray_info_idx": fil[2], "force_color_match": True}
        misses = scheduler._missing_force_color_pairs(1, [override], self._raw(tray))
        filament = todo_filament_from_requirement(override)
        assert tray_fits_filament(_slot(0, 0, tray[0], tray[1], tray[2]), filament) == (not misses)

    @pytest.mark.parametrize(("fil", "tray"), CASES)
    def test_a_fitting_tray_is_one_the_matcher_takes(self, fil, tray):
        scheduler = PrintScheduler()
        req = {"slot_id": 1, "type": fil[0], "color": fil[1], "tray_info_idx": fil[2], "force_color_match": fil[3]}
        loaded = [
            {
                "type": tray[0],
                "color": tray[1],
                "tray_info_idx": tray[2],
                "global_tray_id": 0,
                "extruder_id": None,
                "remain": -1,
            }
        ]
        mapping = scheduler._match_filaments_to_slots([req], loaded, quiet=True)
        filament = todo_filament_from_requirement(req)
        if tray_fits_filament(_slot(0, 0, tray[0], tray[1], tray[2]), filament):
            assert mapping == [0]


class TestBuildTodoKeepsShortAndMissingApart:
    JOBS = [
        TodoJob(1, "A", frozenset({1}), 1, None, None, False),
        TodoJob(2, "B", frozenset({1}), 1, None, None, False),
    ]

    def _build(self, holds, hints=None, jobs=None):
        return build_todo(jobs or self.JOBS, {1: "Farm A1", 2: "Farm B"}, holds, [], {}, [], slot_hints=hints or {})

    def test_a_short_and_a_missing_entry_of_one_filament_are_two_entries(self):
        holds = {
            1: [FilamentHold(1, 1, None, (_short([ShortTray(0, 1, 12.0)]),))],
            2: [FilamentHold(2, 1, None, (TodoFilament("PLA", LAVA, "Lava Red"),))],
        }
        body = self._build(holds)
        assert body["count"] == 2
        entries = body["groups"][0]["entries"]
        assert [e["filaments"][0]["short"] for e in entries] == [True, False]

    def test_the_short_filament_carries_its_trays_and_grams(self):
        holds = {1: [FilamentHold(1, 1, None, (_short([ShortTray(0, 1, 12.0), ShortTray(0, 2, 13.0)], 60.0),))]}
        (entry,) = self._build(holds, {1: _farm_hint()})["groups"][0]["entries"]
        assert entry["filaments"][0]["short"] is True
        assert entry["filaments"][0]["required_grams"] == 60.0
        assert entry["filaments"][0]["short_trays"] == [
            {"ams_id": 0, "tray_id": 1, "remaining_grams": 12.0},
            {"ams_id": 0, "tray_id": 2, "remaining_grams": 13.0},
        ]
        assert entry["slot_hint"]["state"] == HINT_REPLACE

    def test_two_jobs_short_on_different_trays_name_both(self):
        # Short spools in different trays are two entries (upstream 874a703ad),
        # each naming its own tray.
        holds = {
            1: [FilamentHold(1, 1, None, (_short([ShortTray(0, 1, 12.0)]),))],
            2: [FilamentHold(2, 1, None, (_short([ShortTray(0, 2, 7.0)]),))],
        }
        entries = self._build(holds, {1: _farm_hint()})["groups"][0]["entries"]
        assert [(e["jobs"][0]["id"], _ids(e["slot_hint"])) for e in entries] == [(1, [(0, 1)]), (2, [(0, 2)])]

    def test_a_model_entry_names_each_printers_own_tray(self):
        jobs = [TodoJob(1, "Any", frozenset({1, 2}), None, "p1s", "P1S", False)]
        holds = {
            1: [
                FilamentHold(1, 1, "P1S", (_short([ShortTray(0, 1, 12.0)]),)),
                FilamentHold(1, 2, "P1S", (_short([ShortTray(0, 2, 9.0)]),)),
            ]
        }
        hints = {1: _farm_hint(), 2: replace(_farm_hint(), printer_id=2)}
        (entry,) = self._build(holds, hints, jobs)["groups"][0]["entries"]
        assert entry["filaments"][0]["short"] is True
        assert entry["filaments"][0]["short_trays"] == []
        by_printer = {h["printer_id"]: h for h in entry["slot_hints"]}
        assert {pid: (h["state"], _ids(h)) for pid, h in by_printer.items()} == {
            1: (HINT_REPLACE, [(0, 1)]),
            2: (HINT_REPLACE, [(0, 2)]),
        }

    def test_the_count_is_the_one_of_the_entries(self):
        # The same two jobs held on a missing filament: one entry, as before.
        holds = {i: [FilamentHold(i, 1, None, (TodoFilament("PLA", LAVA, "Lava Red"),))] for i in (1, 2)}
        assert self._build(holds)["count"] == 1


class TestShortRowsStayApart:
    def test_a_carried_hold_keeps_two_short_rows_of_one_filament(self):
        a2 = _short([ShortTray(0, 1, 12.0)])
        a3 = _short([ShortTray(0, 2, 13.0)])
        scheduler = PrintScheduler()
        scheduler._pass_holds = {}
        scheduler._filament_holds = {5: [FilamentHold(5, 1, None, (a2, a3))]}
        item = MagicMock(id=5, printer_id=1, target_model=None)
        assert scheduler._carry_filament_hold(item)
        (hold,) = scheduler._pass_holds[5]
        assert [f.short_trays for f in hold.filaments] == [a2.short_trays, a3.short_trays]

    def test_a_short_and_a_missing_row_stay_separate_when_carried(self):
        short = _short([ShortTray(0, 1, 12.0)])
        missing = TodoFilament("PLA", LAVA, "Lava Red")
        scheduler = PrintScheduler()
        scheduler._pass_holds = {}
        scheduler._filament_holds = {
            5: [FilamentHold(5, 1, None, (short,)), FilamentHold(5, 1, None, (missing, short))]
        }
        scheduler._carry_filament_hold(MagicMock(id=5, printer_id=1, target_model=None))
        (hold,) = scheduler._pass_holds[5]
        assert [f.short for f in hold.filaments] == [True, False]

    def test_the_same_row_twice_is_one(self):
        short = _short([ShortTray(0, 1, 12.0)])
        assert unique_filaments([short], [replace(short, required_grams=40.0)]) == [short]

    def test_merging_takes_the_larger_requirement_whether_or_not_trays_are_added(self):
        base = (_short([ShortTray(0, 1, 12.0)], required=30.0),)
        same_tray = (_short([ShortTray(0, 1, 12.0)], required=50.0),)
        assert _merge_short(base, same_tray)[0].required_grams == 50.0
        assert _merge_short(same_tray, base)[0].required_grams == 50.0
        new_tray = (_short([ShortTray(0, 2, 9.0)], required=20.0),)
        merged = _merge_short(base, new_tray)[0]
        assert (merged.required_grams, len(merged.short_trays)) == (30.0, 2)
        unknown = (_short([ShortTray(0, 1, 12.0)], required=None),)
        assert _merge_short(base, unknown)[0].required_grams == 30.0


class TestFromTheDeficit:
    """The deficit check's rows become the entry's short filament."""

    @staticmethod
    async def _todo(deficit, requirements=None):
        scheduler = PrintScheduler()
        req = requirements or [{"slot_id": 1, "type": "PLA", "color": LAVA, "color_name": "Lava Red", "used_grams": 30}]
        scheduler._get_filament_requirements = AsyncMock(return_value=[dict(r) for r in req])
        scheduler._apply_filament_overrides = MagicMock()
        return await scheduler._deficit_todo_filaments(AsyncMock(), MagicMock(id=5), deficit)

    @pytest.mark.asyncio
    async def test_the_mapped_tray_and_its_grams(self):
        (fil,) = await self._todo([FilamentDeficit(1, 0, 1, "PLA", 30.0, 12.0)])
        assert (fil.type, fil.color, fil.color_name) == ("PLA", LAVA, "Lava Red")
        assert fil.short is True
        assert fil.short_trays == (ShortTray(0, 1, 12.0),)
        assert fil.required_grams == 30.0

    @pytest.mark.asyncio
    async def test_rows_of_one_pool_are_one_filament(self):
        pool = ((0, 1, 12.0), (0, 2, 13.0))
        rows = [
            FilamentDeficit(1, 0, 1, "PLA", 30.0, 12.0, pooled=pool),
            FilamentDeficit(2, 0, 2, "PLA", 30.0, 13.0, pooled=pool),
        ]
        req = [
            {"slot_id": 1, "type": "PLA", "color": LAVA, "color_name": "Lava Red"},
            {"slot_id": 2, "type": "PLA", "color": LAVA, "color_name": "Lava Red"},
        ]
        (fil,) = await self._todo(rows, req)
        assert fil.short_trays == (ShortTray(0, 1, 12.0), ShortTray(0, 2, 13.0))
        assert fil.required_grams == 60.0

    @pytest.mark.asyncio
    async def test_rows_without_a_pool_stay_separate(self):
        rows = [FilamentDeficit(1, 0, 1, "PLA", 30.0, 12.0), FilamentDeficit(2, 0, 2, "PLA", 20.0, 13.0)]
        todo = await self._todo(rows)
        assert [(f.short_trays, f.required_grams) for f in todo] == [
            ((ShortTray(0, 1, 12.0),), 30.0),
            ((ShortTray(0, 2, 13.0),), 20.0),
        ]

    def test_the_description_names_the_facts(self):
        pool = ((0, 1, 12.0), (0, 2, 13.0))
        rows = [FilamentDeficit(1, 0, 1, "PLA", 30.0, 12.0, pooled=pool)]
        facts = describe_deficit(rows, color=LAVA, color_name="Lava Red")
        assert (facts.filament_type, facts.color_name, facts.required_grams) == ("PLA", "Lava Red", 30.0)
        assert facts.remaining_grams == 25.0
        unknown = describe_deficit([FilamentDeficit(1, 0, 1, "PLA", 30.0, None)])
        assert unknown.remaining_grams is None

    @pytest.mark.asyncio
    async def test_a_hold_rebuilt_after_a_restart_carries_the_fields(self):
        scheduler = PrintScheduler()
        scheduler._pass_holds = {}
        scheduler._get_filament_requirements = AsyncMock(
            return_value=[{"slot_id": 1, "type": "PLA", "color": LAVA, "color_name": "Lava Red"}]
        )
        scheduler._apply_filament_overrides = MagicMock()
        item = MagicMock(
            id=41, printer_id=8, target_model=None, filament_short=True, filament_overrides=None, waiting_reason=""
        )
        deficit = [FilamentDeficit(1, 0, 1, "PLA", 30.0, 12.0)]
        with patch(
            "backend.app.services.print_scheduler.compute_deficit_for_queue_item", AsyncMock(return_value=deficit)
        ):
            await scheduler._rebuild_filament_hold(AsyncMock(), item)
        (hold,) = scheduler._pass_holds[41]
        assert hold.filaments[0].short is True
        assert hold.filaments[0].short_trays == (ShortTray(0, 1, 12.0),)
        assert hold.filaments[0].required_grams == 30.0


class TestThePoolOfADeficit:
    """compute_deficit_for_queue_item names the trays the pool counted."""

    @staticmethod
    async def _deficit(db_session, printer, tmp_path, backup_on):
        archive = await _setup_archive_3mf(
            db_session, tmp_path, [{"id": "1", "type": "PLA", "color": "#000000", "used_g": "1500.0"}]
        )
        a = await _spool(db_session, label_weight=1000, weight_used=900.0, slicer_filament="GFA00")
        b = await _spool(db_session, label_weight=1000, weight_used=700.0, slicer_filament="GFA00")
        await _assign(db_session, printer_id=printer.id, spool_id=a.id, ams_id=0, tray_id=0)
        await _assign(db_session, printer_id=printer.id, spool_id=b.id, ams_id=1, tray_id=0)
        item = await _queue_item(db_session, printer_id=printer.id, archive=archive, ams_mapping=[0])
        patches = TestFilamentDeficitBackupAware._patch_status(printer_id=printer.id, backup_on=backup_on, model="X1C")
        with patch("backend.app.services.filament_deficit.app_settings.base_dir", Path("/")):
            for p in patches:
                p.start()
            try:
                return await compute_deficit_for_queue_item(db_session, item)
            finally:
                for p in patches:
                    p.stop()

    @pytest.mark.asyncio
    async def test_with_backup_every_pooled_tray_is_named(self, db_session, printer_factory, tmp_path):
        printer = await printer_factory(model="X1C")
        (row,) = await self._deficit(db_session, printer, tmp_path, True)
        assert row.pooled == ((0, 0, 100.0), (1, 0, 300.0))
        assert describe_deficit([row]).trays == (ShortTray(0, 0, 100.0), ShortTray(1, 0, 300.0))

    @pytest.mark.asyncio
    async def test_without_backup_only_the_mapped_tray(self, db_session, printer_factory, tmp_path):
        printer = await printer_factory(model="X1C")
        (row,) = await self._deficit(db_session, printer, tmp_path, False)
        assert row.pooled == ()
        assert describe_deficit([row]).trays == (ShortTray(0, 0, 100.0),)
        # Not part of the dict the routes serve.
        assert "pooled" not in row.to_dict()


class TestTheHintIsKeptWhenOnlyGramsChange:
    @pytest.mark.asyncio
    async def test_the_memo_is_reused_and_carries_every_loaded_slot(self):
        scheduler = _scheduler_with({1: _need(RED)})
        scheduler._planned_mapping = AsyncMock(wraps=scheduler._planned_mapping)
        statuses = {1: _status(_loaded_ams(RED, "FF69B4", WHITE, GREEN))}
        pink = TodoFilament("PLA", "#FF69B4", "Pink", short=True, short_trays=(ShortTray(0, 1, 12.0),))
        first = (await _hints(scheduler, statuses, [_job(1)], _holds(1, filaments=(pink,))))[1]
        later = replace(pink, short_trays=(ShortTray(0, 1, 4.0),))
        second = (await _hints(scheduler, statuses, [_job(1)], _holds(1, filaments=(later,))))[1]
        assert scheduler._planned_mapping.await_count == 1
        assert second is first
        assert [(s.ams_id, s.tray_id) for s in first.loaded] == [(0, 0), (0, 1), (0, 2), (0, 3)]
        assert _hint_dict(first, (pink,), {})["slots"][0]["remaining_grams"] == 12.0
        assert _hint_dict(second, (later,), {})["slots"][0]["remaining_grams"] == 4.0

    @pytest.mark.asyncio
    async def test_a_dual_nozzle_hint_keeps_the_loaded_slots_of_both(self):
        scheduler = _scheduler_with({1: _need(RED)})
        ams = [
            {"id": 0, "tray": [_tray(0, "PLA", RED), _tray(1, "PLA", WHITE)]},
            {"id": 1, "tray": [_tray(0, "PLA", GREEN), _tray(1, exists=False)]},
        ]
        hint = (await _hints(scheduler, {1: _dual(ams)}, [_job(1)], _holds(1)))[1]
        assert {(s.ams_id, s.tray_id, s.nozzle) for s in hint.loaded} == {
            (0, 0, "right"),
            (0, 1, "right"),
            (1, 0, "left"),
        }
