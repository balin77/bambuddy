"""The AMS picture of the To do list (#3726): every slot, where each filament goes, additive on the entry."""

import pytest

from backend.app.schemas.print_queue import QueueTodoResponse
from backend.app.services.queue_todo import (
    HINT_ALL_NEEDED,
    HINT_FREE,
    HINT_REPLACEABLE,
    FilamentHold,
    PictureSlot,
    ShortTray,
    SlotExtra,
    SlotHint,
    TodoFilament,
    TodoJob,
    _hint_dict,
    build_todo,
    picture_dict,
)
from backend.tests.unit.test_prepare_step_prepare import RED_PINK, _next_job, _prepare, _printing
from backend.tests.unit.test_slot_hints_3634 import (
    BLUE,
    GREEN,
    PINK,
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


def _open(picture):
    return [u["ams_id"] for u in picture["units"] if not u["collapsed"]]


def _slots_of(picture):
    return {(s["ams_id"], s["tray_id"]): s for u in picture["units"] for s in u["slots"]}


def _states(picture):
    return {key: s["state"] for key, s in _slots_of(picture).items()}


def _todo_job(item_id=1, pinned=1, ids=(1,), **fields):
    return TodoJob(item_id, f"Lamp_{item_id}.3mf", frozenset(ids), pinned, None, None, False, **fields)


async def _picture(statuses, fils=(PINK,), requirements=None, others=(), printer=1, extras=None):
    scheduler = _scheduler_with(requirements or {1: _need(RED)})
    hints = await _hints(scheduler, statuses, [_job(1), *others], _holds(printer, filaments=fils))
    hint = hints[printer]
    return hint, picture_dict(hint, printer, "Shelf P1S right", fils, extras)


class TestSlots:
    @pytest.mark.asyncio
    async def test_every_slot_is_drawn_with_its_state_and_the_new_spool_stands_on_its_slot(self):
        ams = [
            {
                "id": 0,
                "tray": [
                    _tray(0, "PLA", RED),
                    _tray(1, "PLA", BLUE),
                    _tray(2, "PLA", WHITE),
                    _tray(3, exists=False),
                ],
            }
        ]
        hint, picture = await _picture({1: _status(ams, state="RUNNING", print_ams_mapping=[0], tray_now=0)})
        # The hint offers the empty slot; the picture puts the spool above it.
        assert [(s.ams_id, s.tray_id) for s in hint.slots] == [(0, 3)]
        slots = _slots_of(picture)
        assert sorted(slots) == [(0, 0), (0, 1), (0, 2), (0, 3)]
        assert _states(picture) == {(0, 0): "locked", (0, 1): "keep", (0, 2): "keep", (0, 3): "empty"}
        assert slots[(0, 3)]["incoming"]["filament_index"] == 0
        assert slots[(0, 3)]["incoming"]["color"] == "#FF69B4"
        assert [key for key, s in slots.items() if s["incoming"]] == [(0, 3)]

    @pytest.mark.asyncio
    async def test_a_loaded_slot_no_job_needs_goes_out_when_nothing_is_free(self):
        ams = _loaded_ams(RED, BLUE, WHITE, GREEN)
        hint, picture = await _picture(
            {1: _status(ams)}, requirements={1: _need(RED), 2: _need(BLUE, WHITE)}, others=[_job(2)]
        )
        assert hint.state == HINT_REPLACEABLE
        assert _states(picture) == {(0, 0): "keep", (0, 1): "keep", (0, 2): "keep", (0, 3): "out"}
        assert _slots_of(picture)[(0, 3)]["incoming"]["filament_index"] == 0

    @pytest.mark.asyncio
    async def test_a_slot_the_printer_cannot_read_is_unknown_and_never_a_target(self):
        ams = [{"id": 0, "tray": [_tray(0, "PLA", RED), _tray(1, exists=True), _tray(2, exists=False)]}]
        _hint, picture = await _picture({1: _status(ams)})
        assert _states(picture) == {(0, 0): "keep", (0, 1): "unknown", (0, 2): "empty"}
        assert _slots_of(picture)[(0, 2)]["incoming"] is not None

    @pytest.mark.asyncio
    async def test_a_slot_that_holds_what_the_entry_needs_fits(self):
        ams = _loaded_ams(RED, BLUE, "FF69B4", GREEN)
        ams[0]["tray"][1]["exists"] = False
        ams[0]["tray"][1]["tray_type"] = ""
        _hint, picture = await _picture({1: _status(ams)})
        assert _states(picture)[(0, 2)] == "fits"
        assert _states(picture)[(0, 1)] == "empty"

    @pytest.mark.asyncio
    async def test_the_slots_of_a_short_spool_go_out_and_the_new_spool_stands_on_the_first(self):
        ams = _loaded_ams(RED, BLUE, WHITE, GREEN)
        short = TodoFilament(
            "PLA", "#0000FF", "Blue", short=True, short_trays=(ShortTray(0, 1, 12.0),), required_grams=505
        )
        _hint, picture = await _picture({1: _status(ams)}, fils=(short,))
        assert _states(picture) == {(0, 0): "keep", (0, 1): "out", (0, 2): "keep", (0, 3): "keep"}
        slot = _slots_of(picture)[(0, 1)]
        assert slot["incoming"]["required_g"] == 505
        # The grams of the short tray come with the entry when the inventory has none.
        assert slot["remaining_g"] == 12.0

    @pytest.mark.asyncio
    async def test_grams_and_looks_of_an_assigned_spool(self):
        ams = _loaded_ams(RED, BLUE)
        extras = {(1, 0, 1): SlotExtra(227.0, "FF0000,0000FF", "sparkle", "Multicolor", "Cotton White")}
        _hint, picture = await _picture({1: _status(ams)}, extras=extras)
        slot = _slots_of(picture)[(0, 1)]
        assert (slot["remaining_g"], slot["extra_colors"], slot["effect_type"], slot["color_name"]) == (
            227.0,
            "FF0000,0000FF",
            "sparkle",
            "Cotton White",
        )
        # No assigned spool and no short tray: no grams, never an invented number.
        assert _slots_of(picture)[(0, 0)]["remaining_g"] is None

    @pytest.mark.asyncio
    async def test_the_rfid_flag_and_the_printers_own_percentage(self):
        ams = [
            {
                "id": 0,
                "tray": [
                    _tray(0, "PLA", RED, tray_uuid="A1" * 16, remain=80),
                    _tray(1, "PLA", BLUE, tray_uuid="0" * 32, tag_uid="0" * 16, remain=-1),
                ],
            }
        ]
        _hint, picture = await _picture({1: _status(ams)})
        slots = _slots_of(picture)
        assert (slots[(0, 0)]["rfid"], slots[(0, 0)]["remain_percent"]) == (True, 80)
        assert (slots[(0, 1)]["rfid"], slots[(0, 1)]["remain_percent"]) == (False, None)


class TestPlacementAgainstTheHint:
    @pytest.mark.asyncio
    async def test_a_running_print_on_every_ams_tray_and_a_loaded_external_spool_leave_no_slot(self):
        ams = _loaded_ams(RED, BLUE, WHITE, GREEN)
        vt = [{"id": 254, "tray_type": "PETG", "tray_color": "00FF00FF", "tray_info_idx": ""}]
        running = _status(ams, vt=vt, state="RUNNING", print_ams_mapping=[0, 1, 2, 3], tray_now=0)
        scheduler = _scheduler_with({1: _need(RED)})
        hint = (await _hints(scheduler, {1: running}, [_job(1)], _holds(1)))[1]
        # The scheduler says every slot is needed: the external holder is not offered while an AMS slot exists.
        assert hint.state == HINT_ALL_NEEDED
        picture = picture_dict(hint, 1, "P", (PINK,))
        assert picture["unplaced"] == [0]
        assert not [k for k, s in _slots_of(picture).items() if s["incoming"] or s["state"] == "out"]
        assert _states(picture)[(255, 0)] == "keep"

    @pytest.mark.asyncio
    async def test_a_short_spool_in_a_tray_of_the_running_print_is_locked_and_has_no_slot(self):
        ams = _loaded_ams(RED, BLUE, WHITE, GREEN)
        running = _status(ams, state="RUNNING", print_ams_mapping=[1], tray_now=1)
        short = TodoFilament(
            "PLA", "#0000FF", "Blue", short=True, short_trays=(ShortTray(0, 1, 12.0),), required_grams=505
        )
        scheduler = _scheduler_with({1: _need(BLUE)})
        hint = (await _hints(scheduler, {1: running}, [_job(1)], _holds(1, filaments=(short,))))[1]
        picture = picture_dict(hint, 1, "P", (short,))
        assert _states(picture)[(0, 1)] == "locked"
        assert picture["unplaced"] == [0]
        assert not [k for k, s in _slots_of(picture).items() if s["incoming"]]

    @pytest.mark.asyncio
    async def test_each_external_holder_of_a_two_nozzle_printer_is_a_unit_with_its_nozzle(self):
        ams = [{"id": 0, "tray": [_tray(0, "PLA", RED)]}]
        vt = [
            {"id": 254, "tray_type": "PETG", "tray_color": "00FF00FF", "tray_info_idx": ""},
            {"id": 255, "tray_type": "PLA", "tray_color": "0000FFFF", "tray_info_idx": ""},
        ]
        scheduler = _scheduler_with({1: _need(RED)})
        hint = (await _hints(scheduler, {1: _dual(ams, vt=vt)}, [_job(1)], _holds(1)))[1]
        units = picture_dict(hint, 1, "P", (PINK,))["units"]
        external = [
            (u["ams_id"], u["kind"], u["nozzle"], [s["tray_id"] for s in u["slots"]])
            for u in units
            if u["kind"] == "external"
        ]
        assert external == [(255, "external", "left", [0]), (255, "external", "right", [1])]


class TestUnits:
    AMS_AB = [
        {
            "id": 0,
            "tray": [_tray(0, "PLA", RED), _tray(1, "PLA", BLUE), _tray(2, "PLA", WHITE), _tray(3, "PLA", GREEN)],
        },
        {
            "id": 1,
            "tray": [_tray(0, "PLA", RED), _tray(1, exists=False), _tray(2, "PLA", WHITE), _tray(3, "PLA", GREEN)],
        },
    ]

    @pytest.mark.asyncio
    async def test_only_the_unit_something_goes_into_is_listed_the_other_is_collapsed(self):
        _hint, picture = await _picture({1: _status(self.AMS_AB)})
        assert _open(picture) == [1]
        assert [(u["ams_id"], u["kind"], len(u["slots"])) for u in picture["units"] if u["collapsed"]] == [
            (0, "ams", 4)
        ]

    @pytest.mark.asyncio
    async def test_with_nothing_placed_the_first_unit_is_shown(self):
        ams = [{"id": 0, "tray": [_tray(0, "PLA", RED)]}, {"id": 1, "tray": [_tray(0, "PLA", BLUE)]}]
        scheduler = _scheduler_with({1: _need(RED), 2: _need(BLUE)})
        hint = (await _hints(scheduler, {1: _status(ams)}, [_job(1), _job(2)], _holds(1)))[1]
        picture = picture_dict(hint, 1, "P", (PINK,))
        assert _open(picture) == [0]
        assert picture["unplaced"] == [0]

    @pytest.mark.asyncio
    async def test_each_ams_ht_is_a_unit_and_the_external_holder_comes_last(self):
        ams = [
            {"id": 0, "tray": [_tray(0, "PLA", RED), _tray(1, "PLA", BLUE)]},
            {"id": 128, "tray": [_tray(0, "PLA", WHITE)]},
            {"id": 129, "tray": [_tray(0, exists=False)]},
        ]
        vt = [{"id": 254, "tray_type": "PETG", "tray_color": "00FF00FF", "tray_info_idx": ""}]
        _hint, picture = await _picture({1: _status(ams, vt=vt)})
        assert [(u["ams_id"], u["kind"]) for u in picture["units"]] == [
            (0, "ams"),
            (128, "ht"),
            (129, "ht"),
            (255, "external"),
        ]
        assert _open(picture) == [129]
        assert _slots_of(picture)[(129, 0)]["is_ht"] is True

    @pytest.mark.asyncio
    async def test_the_external_holder_is_keyed_as_the_inventory_stores_it(self):
        vt = [{"id": 254, "tray_type": "PETG", "tray_color": "00FF00FF", "tray_info_idx": ""}]
        scheduler = _scheduler_with({1: _need(RED)})
        hint = (await _hints(scheduler, {1: _status(vt=vt)}, [_job(1)], _holds(1)))[1]
        picture = picture_dict(hint, 1, "P", (PINK,))
        (unit,) = picture["units"]
        assert (unit["ams_id"], unit["kind"], unit["slots"][0]["is_external"]) == (255, "external", True)
        assert unit["slots"][0]["tray_id"] == 0

    @pytest.mark.asyncio
    async def test_dual_nozzle_units_name_their_nozzle_and_a_filament_goes_to_its_own(self):
        left = TodoFilament("PLA", "#FF69B4", "Pink", nozzle=1)
        right = TodoFilament("PLA", "#FF69B4", "Pink", nozzle=0)
        ams = [
            {"id": 0, "tray": [_tray(i, "PLA", c) for i, c in enumerate((RED, BLUE, WHITE, GREEN))]},
            {
                "id": 1,
                "tray": [_tray(0, "PLA", RED), _tray(1, exists=False), _tray(2, "PLA", WHITE), _tray(3, "PLA", GREEN)],
            },
        ]
        scheduler = _scheduler_with({1: _need(RED)})
        hint = (await _hints(scheduler, {1: _dual(ams)}, [_job(1)], _holds(1, filaments=(left,))))[1]
        picture = picture_dict(hint, 1, "P", (left,))
        assert {u["ams_id"]: u["nozzle"] for u in picture["units"]} == {
            0: "right",
            1: "left",
        }
        assert _slots_of(picture)[(1, 1)]["incoming"] is not None
        # Naming the right nozzle: never the free slot of the left one.
        on_right = picture_dict(hint, 1, "P", (right,))
        (target,) = [k for k, s in _slots_of(on_right).items() if s["incoming"]]
        assert target[0] == 0
        assert _slots_of(on_right)[target]["state"] == "out"

    @pytest.mark.asyncio
    async def test_a_filament_track_switch_lifts_the_nozzle_filter_but_not_the_labels(self):
        right = TodoFilament("PLA", "#FF69B4", "Pink", nozzle=0)
        ams = [
            {"id": 0, "tray": [_tray(i, "PLA", c) for i, c in enumerate((RED, BLUE, WHITE, GREEN))]},
            {"id": 1, "tray": [_tray(0, "PLA", RED), _tray(1, exists=False)]},
        ]
        scheduler = _scheduler_with({1: _need(RED)})
        hint = (await _hints(scheduler, {1: _dual(ams, fts=True)}, [_job(1)], _holds(1, filaments=(right,))))[1]
        picture = picture_dict(hint, 1, "P", (right,))
        assert _slots_of(picture)[(1, 1)]["incoming"] is not None
        assert {u["nozzle"] for u in picture["units"] if not u["collapsed"]} == {"left"}

    @pytest.mark.asyncio
    async def test_an_ams_3h_lists_its_nine_slots_and_an_ams_lite_its_kind(self):
        from backend.app.utils.tray_ids import AMS3H_UNIT_ID

        trays = [_tray(i, "PLA", RED) for i in range(8)] + [_tray(8, exists=False)]
        ams = [{"id": AMS3H_UNIT_ID, "ams_type": 6, "tray": trays}]
        scheduler = _scheduler_with({1: _need(RED)})
        hint = (await _hints(scheduler, {1: _status(ams)}, [_job(1)], _holds(1)))[1]
        (unit,) = picture_dict(hint, 1, "P", (PINK,))["units"]
        assert (unit["kind"], len(unit["slots"])) == ("ams3h", 9)
        lite = [{"id": 0, "ams_type": 2, "tray": [_tray(0, "PLA", RED), _tray(1, exists=False)]}]
        hint = (await _hints(scheduler, {1: _status(lite)}, [_job(1)], _holds(1)))[1]
        assert picture_dict(hint, 1, "P", (PINK,))["units"][0]["kind"] == "ams_lite"


class TestEntries:
    def _entry(self, todo, kind="load_filament"):
        return next(e for g in todo["groups"] for e in g["entries"] if e["kind"] == kind)

    @pytest.mark.asyncio
    async def test_a_load_entry_carries_the_picture_and_the_schema_keeps_it(self):
        ams = _loaded_ams(RED, BLUE, WHITE, GREEN)
        scheduler = _scheduler_with({1: _need(RED)})
        hints = await _hints(scheduler, {1: _status(ams)}, [_job(1)], _holds(1))
        todo = build_todo(
            [_todo_job(101)],
            {1: "Shelf P1S right"},
            _holds(1),
            [],
            {},
            [],
            hints,
            None,
            {(1, 0, 1): SlotExtra(620.0)},
            lambda f: 2,
        )
        picture = self._entry(todo)["ams_picture"]
        assert picture["printer_name"] == "Shelf P1S right"
        incoming = next(s["incoming"] for s in _slots_of(picture).values() if s["incoming"])
        assert (incoming["stock_count"], incoming["filament_index"]) == (2, 0)
        parsed = QueueTodoResponse.model_validate(todo)
        assert [s.state for s in parsed.groups[0].entries[0].ams_picture.units[0].slots] == [
            "keep",
            "out",
            "keep",
            "keep",
        ]

    @pytest.mark.asyncio
    async def test_the_picture_changes_neither_the_count_nor_the_hint_nor_the_list_entry(self):
        from unittest.mock import patch

        ams = _loaded_ams(RED, BLUE, WHITE, GREEN)

        async def hint_of(with_picture):
            scheduler = _scheduler_with({1: _need(RED)})
            if with_picture:
                return (await _hints(scheduler, {1: _status(ams)}, [_job(1)], _holds(1)))[1]
            # The scheduler as it was before the picture: nothing is added to the hint.
            with patch("backend.app.services.print_scheduler._with_picture", lambda hint, *a, **k: hint):
                return (await _hints(scheduler, {1: _status(ams)}, [_job(1)], _holds(1)))[1]

        hint, bare = await hint_of(True), await hint_of(False)
        assert hint.picture and not bare.picture
        # What the scheduler decides is the same, field by field.
        assert (hint.state, hint.slots, hint.by_nozzle, hint.loaded, hint.unknown_job_ids) == (
            bare.state,
            bare.slots,
            bare.by_nozzle,
            bare.loaded,
            bare.unknown_job_ids,
        )
        assert (hint.state, [(s.ams_id, s.tray_id) for s in hint.slots]) == (HINT_REPLACEABLE, [(0, 1), (0, 2), (0, 3)])
        args = ([_todo_job(101)], {1: "P"}, _holds(1), [], {}, [])
        with_picture = build_todo(*args, {1: hint})
        without = build_todo(*args, {1: bare})
        assert with_picture["count"] == without["count"] == 1
        entry, plain = self._entry(with_picture), self._entry(without)
        assert entry.pop("ams_picture") is not None and plain.pop("ams_picture") is None
        assert entry == plain
        assert entry["slot_hint"] == _hint_dict(bare, (PINK,), {101: 0})

    @pytest.mark.asyncio
    async def test_a_kept_hint_gets_the_slots_as_they_are_now(self):
        from unittest.mock import AsyncMock

        scheduler = _scheduler_with({1: _need(RED)})
        ams = _loaded_ams(RED, BLUE)
        ams[0]["tray"][1]["remain"] = 80
        first = (await _hints(scheduler, {1: _status(ams)}, [_job(1)], _holds(1)))[1]
        assert _slots_of(picture_dict(first, 1, "P", (PINK,)))[(0, 1)]["remain_percent"] == 80
        # The printer's own percentage is not part of what the hint is computed
        # from: the second pass keeps the hint, and the picture still follows.
        ams[0]["tray"][1]["remain"] = 40
        compute = AsyncMock(side_effect=AssertionError("the hint is kept, not computed again"))
        scheduler._slot_hint_for_printer = compute
        second = (await _hints(scheduler, {1: _status(ams)}, [_job(1)], _holds(1)))[1]
        compute.assert_not_called()
        assert second.slots == first.slots
        assert _slots_of(picture_dict(second, 1, "P", (PINK,)))[(0, 1)]["remain_percent"] == 40

    @pytest.mark.asyncio
    async def test_the_picture_names_no_job_and_no_spool_of_the_inventory(self):
        ams = _loaded_ams(RED, BLUE)
        scheduler = _scheduler_with({1: _need(RED)})
        hints = await _hints(scheduler, {1: _status(ams)}, [_job(1)], _holds(1))
        todo = build_todo([_todo_job(101)], {1: "P"}, _holds(1), [], {}, [], hints, None, {(1, 0, 0): SlotExtra(100.0)})
        text = repr(self._entry(todo)["ams_picture"])
        assert "Lamp_101" not in text and "job" not in text and "spool_id" not in text

    @pytest.mark.asyncio
    async def test_a_model_entry_lists_the_idle_printer_with_the_fewest_spools_to_take_out_first(self):
        full = _loaded_ams(RED, BLUE, WHITE, GREEN)
        free = [{"id": 0, "tray": [_tray(0, "PLA", RED), _tray(1, exists=False)]}]
        scheduler = _scheduler_with({1: _need(RED)})
        holds = {101: [FilamentHold(101, pid, "P1S", (PINK,)) for pid in (1, 2, 3)]}
        hints = await _hints(scheduler, {1: _status(full), 2: _status(full), 3: _status(free)}, [_job(1, None)], holds)
        job = TodoJob(101, "Lamp_Base.5x.P1S.3mf", frozenset({1, 2, 3}), None, "p1s", "P1S", False)
        names = {1: "Shelf A", 2: "Shelf B", 3: "Shelf C"}
        # Printer 3 has a free slot but is printing: the idle ones come first, fewest "out" next.
        todo = build_todo([job], names, holds, [], {}, [], hints, None, None, None, idle_printers={1, 2})
        pictures = self._entry(todo)["ams_pictures"]
        assert [p["printer_id"] for p in pictures] == [1, 2, 3]
        todo = build_todo([job], names, holds, [], {}, [], hints, None, None, None, idle_printers={1, 3})
        assert [p["printer_id"] for p in self._entry(todo)["ams_pictures"]] == [3, 1, 2]
        assert "ams_picture" not in self._entry(todo) or self._entry(todo).get("ams_picture") is None

    @pytest.mark.asyncio
    async def test_a_printer_that_reported_no_slots_has_no_picture(self):
        assert picture_dict(None, 1, "P", (PINK,)) is None
        assert picture_dict(SlotHint(1, HINT_FREE), 1, "P", (PINK,)) is None


class TestPrepare:
    @pytest.mark.asyncio
    async def test_a_prepare_line_has_a_compact_picture_that_leaves_the_running_print_s_slot_locked(self):
        ams = _loaded_ams(RED, BLUE, WHITE, GREEN)
        scheduler = _scheduler_with({2: RED_PINK})
        entries = await _prepare(scheduler, {1: _printing(ams)}, [_next_job(2)])
        todo = build_todo(
            [_todo_job(2)],
            {1: "Shelf P1S right"},
            {},
            [],
            {},
            [],
            None,
            entries,
            None,
            lambda f: 5,
        )
        line = todo["groups"][0]["prepare"][0]
        picture = line["ams_picture"]
        assert picture["compact"] is True
        states = _states(picture)
        assert states[(0, 0)] == "locked"
        # The line's own slot list and the picture's target agree.
        assert [(s["ams_id"], s["tray_id"]) for s in line["slot_hint"]["slots"]][0] == next(
            k for k, s in _slots_of(picture).items() if s["incoming"]
        )
        assert _slots_of(picture)[(0, 1)]["incoming"]["stock_count"] is None
        assert QueueTodoResponse.model_validate(todo)

    @pytest.mark.asyncio
    async def test_an_empty_prepare_hint_still_draws_the_printer(self):
        picture = picture_dict(
            SlotHint(
                1,
                HINT_FREE,
                picture=(PictureSlot(0, 0, 0, False, False, 1, None, "PLA", "#FF0000"),),
                running=frozenset({0}),
            ),
            1,
            "P",
            (PINK,),
            compact=True,
        )
        assert picture["units"][0]["slots"][0]["state"] == "locked"
        assert picture["unplaced"] == [0]
