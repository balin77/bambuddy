"""Which slot an entry of the To do list is offered (#3634): the printer's hint as one entry shows it."""

import pytest

from backend.app.services.queue_todo import HINT_ALL_NEEDED, HINT_FREE, HINT_REPLACEABLE, TodoFilament, _hint_dict
from backend.tests.unit.test_slot_hints_3634 import (
    PINK,
    RED,
    TestDualNozzle as _Dual,
    _dual,
    _hints,
    _holds,
    _job,
    _need,
    _scheduler_with,
)


class TestEntryHints:
    AMS = _Dual.AMS

    @pytest.mark.asyncio
    async def test_an_entry_for_one_nozzle_is_offered_only_that_nozzle(self):
        left = TodoFilament("PLA", "#FF69B4", "Pink", nozzle=1)
        right = TodoFilament("PLA", "#FF69B4", "Pink", nozzle=0)
        scheduler = _scheduler_with({1: _need(RED)})
        hint = (await _hints(scheduler, {1: _dual(self.AMS)}, [_job(1)], _holds(1)))[1]
        on_left = _hint_dict(hint, (left,), {})
        on_right = _hint_dict(hint, (right,), {})
        assert (on_left["state"], [(s["ams_id"], s["tray_id"], s["nozzle"]) for s in on_left["slots"]]) == (
            HINT_FREE,
            [(1, 1, "left")],
        )
        assert [p["nozzle"] for p in on_left["by_nozzle"]] == ["left"]
        # Right nozzle: AMS A is all loaded; the job takes its red, the rest can go.
        assert on_right["state"] == HINT_REPLACEABLE
        assert {s["nozzle"] for s in on_right["slots"]} == {"right"}

    @pytest.mark.asyncio
    async def test_an_entry_for_both_nozzles_shows_both_parts(self):
        both = (TodoFilament("PLA", "#FF69B4", "Pink", nozzle=0), TodoFilament("PLA", "#FF69B4", "Pink", nozzle=1))
        scheduler = _scheduler_with({1: _need(RED)})
        hint = (await _hints(scheduler, {1: _dual(self.AMS)}, [_job(1)], _holds(1)))[1]
        shown = _hint_dict(hint, both, {})
        assert shown["state"] == HINT_FREE
        assert [(p["nozzle"], p["state"]) for p in shown["by_nozzle"]] == [
            ("right", HINT_REPLACEABLE),
            ("left", HINT_FREE),
        ]

    @pytest.mark.asyncio
    async def test_a_nozzle_without_a_slot_gets_no_hint_never_the_other_nozzle(self):
        # Only the left nozzle has an AMS here.
        only_left = [self.AMS[1]]
        scheduler = _scheduler_with({1: _need(RED)})
        hint = (await _hints(scheduler, {1: _dual(only_left)}, [_job(1)], _holds(1)))[1]
        right = TodoFilament("PLA", "#FF69B4", "Pink", nozzle=0)
        left = TodoFilament("PLA", "#FF69B4", "Pink", nozzle=1)
        assert [p.nozzle for p in hint.by_nozzle] == ["left"]
        assert _hint_dict(hint, (right,), {}) is None
        assert _hint_dict(hint, (left,), {})["state"] == HINT_FREE

    @pytest.mark.asyncio
    async def test_a_filament_that_names_no_nozzle_may_go_anywhere(self):
        # As the matcher reads it: no nozzle on the requirement, no filter.
        anywhere = TodoFilament("PLA", "#FF69B4", "Pink")
        scheduler = _scheduler_with({1: _need(RED)})
        hint = (await _hints(scheduler, {1: _dual(self.AMS)}, [_job(1)], _holds(1)))[1]
        shown = _hint_dict(hint, (anywhere,), {})
        assert shown["by_nozzle"] == []
        assert [(s["ams_id"], s["tray_id"]) for s in shown["slots"]] == [(1, 1)]


class TestVisibleHints:
    def test_the_route_drops_the_hints_of_printers_the_caller_may_not_see(self):
        from backend.app.api.routes.print_queue import visible_slot_hints
        from backend.app.services.queue_todo import SlotHint

        hints = {1: SlotHint(1, HINT_FREE), 2: SlotHint(2, HINT_FREE), 3: SlotHint(3, HINT_ALL_NEEDED)}
        assert set(visible_slot_hints(hints, {1: "A", 3: "C"})) == {1, 3}
        assert visible_slot_hints(hints, {}) == {}

    def test_unknown_jobs_counts_only_the_jobs_in_the_list(self):
        from backend.app.services.queue_todo import SlotHint

        hint = SlotHint(1, HINT_ALL_NEEDED, unknown_job_ids=(5, 6, 7))
        assert _hint_dict(hint, (PINK,), {5, 7})["unknown_jobs"] == 2
        assert _hint_dict(hint, (PINK,), set())["unknown_jobs"] == 0
