"""The scheduler's "To do" records on the farm's own paths (#3615 with #3587 and #3590).

Loaded filament first skips a job instead of holding it; the skip is recorded
structured like the hold is, together with where the job stands in the
priority countdown (the same computation as the suffix of its waiting text).
Stock flags follow the " - none left in inventory" decision of #3590. Only
recording: the waiting texts are covered by their own tests.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.app.services.inventory_stock import StockEntry
from backend.app.services.print_scheduler import PrintScheduler, _filament_wait_state, _filament_wait_suffix
from backend.app.services.queue_todo import (
    FilamentHold,
    TodoFilament,
    merge_todo_filaments,
    priority_state,
    todo_filament_from_requirement,
)
from backend.tests.unit.test_scheduler_loaded_filament_first_3587 import (
    _BROWN,
    _add_item,
    _mode,
    _run,
    ctx,  # noqa: F401 - fixture
)

PLA = TodoFilament("PLA", "")
FORCED = [{"slot_id": 1, "type": "PLA", "color": "#8B5A2B", "color_name": "Earth Brown", "force_color_match": True}]


class TestWaitState:
    """The structured twin of the suffix: they cannot drift apart."""

    @pytest.mark.parametrize("hours", [None, 48, 1])
    @pytest.mark.parametrize("age", [0, 10, 47.5, 49, 500])
    def test_same_computation_as_the_suffix(self, hours, age):
        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc)
        item = MagicMock(created_at=(now - timedelta(hours=age)).replace(tzinfo=None), scheduled_time=None)
        suffix, has_priority = _filament_wait_suffix(item, now, hours)
        state = _filament_wait_state(item, now, hours)
        if state is None:
            assert (suffix, has_priority) == ("", False)
            return
        assert state[0] is has_priority
        assert suffix == (" · has priority" if state[0] else f" · priority in {state[1]} h")

    def test_priority_state_names(self):
        assert priority_state(True, None) == ("has_priority", None)
        assert priority_state(False, 7) == ("priority_in", 7)


class TestPinnedSkipIsRecorded:
    @pytest.mark.asyncio
    async def test_unmatched_filament_skip_records_hold_and_countdown(self, ctx):
        await _mode(ctx)
        item_id = await _add_item(ctx, printer_id=1)
        scheduler = PrintScheduler()
        await _run(ctx, scheduler, unmatched_items={item_id})

        assert scheduler.filament_holds_snapshot()[item_id] == [FilamentHold(item_id, 1, None, (PLA,))]
        assert scheduler.filament_priorities_snapshot()[item_id] == ("priority_in", 38)

    @pytest.mark.asyncio
    async def test_a_forced_colour_carries_its_name(self, ctx):
        await _mode(ctx)
        overrides = json.dumps(FORCED)
        item_id = await _add_item(ctx, printer_id=1, filament_overrides=overrides, ams_mapping=json.dumps([-1]))
        scheduler = PrintScheduler()
        await _run(ctx, scheduler, real_unmatched=True)

        (hold,) = scheduler.filament_holds_snapshot()[item_id]
        assert hold.filaments == (TodoFilament("PLA", "#8B5A2B", "Earth Brown"),)
        assert hold.filaments[0].color_name == "Earth Brown"

    @pytest.mark.asyncio
    async def test_a_deficit_skip_records_the_short_filament_and_priority(self, ctx):
        await _mode(ctx)
        item_id = await _add_item(ctx, printer_id=1, age_hours=49)
        scheduler = PrintScheduler()
        await _run(ctx, scheduler, deficit_items={item_id})

        assert scheduler.filament_holds_snapshot()[item_id] == [FilamentHold(item_id, 1, None, (PLA,))]
        assert scheduler.filament_priorities_snapshot()[item_id] == ("has_priority", None)

    @pytest.mark.asyncio
    async def test_without_a_limit_there_is_no_countdown(self, ctx):
        await _mode(ctx, hours="None")
        item_id = await _add_item(ctx, printer_id=1)
        scheduler = PrintScheduler()
        await _run(ctx, scheduler, unmatched_items={item_id})

        assert item_id in scheduler.filament_holds_snapshot()
        assert item_id not in scheduler.filament_priorities_snapshot()

    @pytest.mark.asyncio
    async def test_records_are_swapped_when_the_job_fits_again(self, ctx):
        await _mode(ctx)
        item_id = await _add_item(ctx, printer_id=1)
        scheduler = PrintScheduler()
        await _run(ctx, scheduler, unmatched_items={item_id})
        assert item_id in scheduler.filament_priorities_snapshot()

        await _run(ctx, scheduler, launched=MagicMock())
        assert scheduler.filament_holds_snapshot() == {}
        assert scheduler.filament_priorities_snapshot() == {}

    @pytest.mark.asyncio
    async def test_the_declined_wake_of_an_offline_printer_is_recorded(self, ctx):
        from types import SimpleNamespace

        await _mode(ctx)
        item_id = await _add_item(ctx, printer_id=1, age_hours=10)
        scheduler = PrintScheduler()
        plug = SimpleNamespace(
            id=1, name="plug", auto_on=True, enabled=True, printer_id=1, ha_entity_id=None, controls_printer_power=True
        )
        entries = [("PLA (Earth Brown)", TodoFilament("PLA", "#8B5A2B", "Earth Brown"))]
        patches = [
            patch.object(scheduler, "_get_smart_plugs", AsyncMock(return_value=[plug])),
            patch.object(scheduler, "_power_on_and_wait", AsyncMock(return_value=False)),
            patch.object(scheduler, "_cached_filament_shortfall", MagicMock(return_value=["PLA (Earth Brown)"])),
            patch.object(scheduler, "_cached_filament_shortfall_entries", MagicMock(return_value=entries)),
        ]
        await _run(ctx, scheduler, connected=lambda pid: pid != 1, extra_patches=patches)

        assert scheduler.filament_holds_snapshot()[item_id] == [
            FilamentHold(item_id, 1, None, (TodoFilament("PLA", "#8B5A2B", "Earth Brown"),))
        ]
        assert scheduler.filament_priorities_snapshot()[item_id] == ("priority_in", 38)


class TestModelPathIsRecorded:
    @pytest.mark.asyncio
    async def test_short_printers_are_filament_waits_with_the_short_filaments(self, ctx):
        await _mode(ctx)
        item_id = await _add_item(ctx)
        scheduler = PrintScheduler()
        with patch.object(scheduler, "_short_filaments_on", AsyncMock(return_value=[PLA])):
            await _run(ctx, scheduler, short={1, 2, 3})

        holds = scheduler.filament_holds_snapshot()[item_id]
        assert sorted(h.printer_id for h in holds) == [1, 2, 3]
        assert {h.filaments for h in holds} == {(PLA,)}
        assert {h.target_model for h in holds} == {"X1C"}
        assert scheduler.filament_priorities_snapshot()[item_id] == ("priority_in", 38)

    @pytest.mark.asyncio
    async def test_a_prioritised_model_job_reports_it_while_it_reserves_a_printer(self, ctx):
        await _mode(ctx)
        item_id = await _add_item(ctx, age_hours=49)
        scheduler = PrintScheduler()
        with patch.object(scheduler, "_short_filaments_on", AsyncMock(return_value=[PLA])):
            await _run(ctx, scheduler, short={1, 2, 3})

        assert scheduler.filament_priorities_snapshot()[item_id] == ("has_priority", None)
        assert item_id in scheduler.filament_holds_snapshot()

    @pytest.mark.asyncio
    async def test_a_full_printer_leaves_no_record(self, ctx):
        await _mode(ctx)
        item_id = await _add_item(ctx)
        scheduler = PrintScheduler()
        await _run(ctx, scheduler, short={1, 2})  # printer 3 is fine: the job starts

        assert item_id not in scheduler.filament_holds_snapshot()
        assert item_id not in scheduler.filament_priorities_snapshot()

    @pytest.mark.asyncio
    async def test_a_race_after_assignment_is_recorded_under_the_printer_it_lost(self, ctx):
        await _mode(ctx)
        item_id = await _add_item(ctx)
        scheduler = PrintScheduler()
        await _run(ctx, scheduler, unmatched_items={item_id})

        (hold,) = scheduler.filament_holds_snapshot()[item_id]
        assert (hold.printer_id, hold.target_model, hold.filaments) == (1, "X1C", (PLA,))
        assert scheduler.filament_priorities_snapshot()[item_id] == ("priority_in", 38)


class TestShortFilamentsOn:
    @pytest.mark.asyncio
    async def test_reads_the_deficit_the_gate_reads(self, ctx):
        from backend.app.services.filament_deficit import FilamentDeficit

        scheduler = PrintScheduler()
        deficit = [FilamentDeficit(1, 0, 0, "PETG", 100.0, 10.0)]
        item = MagicMock(skip_filament_check=False, id=5)
        with (
            patch.object(scheduler, "_compute_ams_mapping_for_printer", AsyncMock(return_value=[0])),
            patch(
                "backend.app.services.print_scheduler.compute_deficit_for_queue_item", AsyncMock(return_value=deficit)
            ),
            patch.object(scheduler, "_get_filament_requirements", AsyncMock(return_value=None)),
        ):
            assert await scheduler._short_filaments_on(AsyncMock(), item, 1) == [TodoFilament("PETG", "")]

    @pytest.mark.asyncio
    async def test_nothing_short_or_unreadable_is_empty(self, ctx):
        scheduler = PrintScheduler()
        item = MagicMock(skip_filament_check=False, id=5)
        with (
            patch.object(scheduler, "_compute_ams_mapping_for_printer", AsyncMock(return_value=[])),
        ):
            assert await scheduler._short_filaments_on(AsyncMock(), item, 1) == []
        with patch.object(scheduler, "_compute_ams_mapping_for_printer", AsyncMock(side_effect=RuntimeError)):
            assert await scheduler._short_filaments_on(AsyncMock(), item, 1) == []
        assert await scheduler._short_filaments_on(AsyncMock(), MagicMock(skip_filament_check=True), 1) == []

    @pytest.mark.asyncio
    async def test_one_deficit_compute_per_item_and_printer_per_pass(self, ctx):
        scheduler = PrintScheduler()
        item = MagicMock(skip_filament_check=False, id=5, archive_id=1, library_file_id=None, plate_id=1)
        item.filament_overrides = None
        compute = AsyncMock(return_value=[])
        with (
            patch.object(scheduler, "_compute_ams_mapping_for_printer", AsyncMock(return_value=[0])),
            patch("backend.app.services.print_scheduler.compute_deficit_for_queue_item", compute),
        ):
            assert await scheduler._filament_short_on(AsyncMock(), item, 1) is False
            assert await scheduler._short_filaments_on(AsyncMock(), item, 1) == []
            assert await scheduler._short_filaments_on(AsyncMock(), item, 1) == []
            await scheduler._short_filaments_on(AsyncMock(), item, 2)
        assert compute.await_count == 2


class TestMergingFilaments:
    def test_the_forced_twin_wins(self):
        loose = TodoFilament("PLA", "#8B5A2B", "Earth Brown")
        forced = TodoFilament("PLA", "#8B5A2B", "Earth Brown", tray_info_idx="GFA00", forced=True)
        into = [loose]
        merge_todo_filaments(into, [forced, forced])
        assert into == [loose]
        assert into[0].forced is True
        assert into[0].tray_info_idx == "GFA00"
        into = [forced]
        merge_todo_filaments(into, [loose])
        assert into[0].forced is True

    def test_other_filaments_are_added(self):
        into = [PLA]
        merge_todo_filaments(into, [TodoFilament("PETG", "")])
        assert [f.type for f in into] == ["PLA", "PETG"]


class TestMatcherShortRecords:
    async def _find(self, ctx, scheduler, short, **kwargs):
        async def is_short(pid):
            return pid in short

        async def short_filaments(pid):
            return [TodoFilament("PETG", "#112233", "Slate")]

        holds: dict[int, list[TodoFilament]] = {}
        with (
            patch("backend.app.services.print_scheduler.printer_manager.is_connected", MagicMock(return_value=True)),
            patch.object(scheduler, "_is_printer_idle", MagicMock(return_value=True)),
        ):
            async with ctx.session_maker() as db:
                result = await scheduler._find_idle_printer_for_model(
                    db,
                    "X1C",
                    set(),
                    is_short=is_short,
                    short_is_missing=True,
                    short_filaments=short_filaments,
                    holds_out=holds,
                    **kwargs,
                )
        return result, holds

    @pytest.mark.asyncio
    async def test_every_short_printer_has_its_filaments(self, ctx):
        (printer_id, reason), holds = await self._find(ctx, PrintScheduler(), {1, 2, 3})
        assert printer_id is None
        assert reason.startswith("Waiting for filament: X1C-1 (needs more filament)")
        assert holds == {pid: [TodoFilament("PETG", "#112233", "Slate")] for pid in (1, 2, 3)}

    @pytest.mark.asyncio
    async def test_a_forced_colour_wait_keeps_the_short_ones_too(self, ctx):
        scheduler = PrintScheduler()

        def pairs(pid, overrides, raw=None):
            return [] if pid == 1 else [("PLA (Red)", FORCED[0])]

        with patch.object(scheduler, "_missing_force_color_pairs", MagicMock(side_effect=pairs)):
            (printer_id, _), holds = await self._find(ctx, scheduler, {1}, filament_overrides=FORCED)
        assert printer_id is None
        assert holds[1] == [TodoFilament("PETG", "#112233", "Slate")]
        assert holds[2][0].type == "PLA"


def _stock(count):
    return [StockEntry("PLA", "#8B5A2B", "", "", "", None, None, None, count, 0.0)]


class TestNoStockFlags:
    """#3590: the flag follows the waiting text's " - none left in inventory", entry by entry."""

    async def _find(self, ctx, scheduler, pairs, short=frozenset(), stock=0):
        async def is_short(pid):
            return pid in short

        async def short_filaments(pid):
            return [TodoFilament("PLA", "#8B5A2B", "Earth Brown", forced=True)]

        holds: dict[int, list[TodoFilament]] = {}
        scheduler._inventory_hints = True
        with (
            patch("backend.app.services.print_scheduler.printer_manager.is_connected", MagicMock(return_value=True)),
            patch.object(scheduler, "_is_printer_idle", MagicMock(return_value=True)),
            patch.object(scheduler, "_missing_force_color_pairs", MagicMock(side_effect=pairs)),
            patch.object(scheduler, "_stock_entries", AsyncMock(return_value=_stock(stock))),
        ):
            async with ctx.session_maker() as db:
                result = await scheduler._find_idle_printer_for_model(
                    db,
                    "X1C",
                    set(),
                    filament_overrides=FORCED,
                    is_short=is_short,
                    short_is_missing=True,
                    short_filaments=short_filaments,
                    holds_out=holds,
                )
        return result, holds

    @pytest.mark.asyncio
    async def test_marked_entries_are_flagged(self, ctx):
        (printer_id, reason), holds = await self._find(
            ctx, PrintScheduler(), lambda pid, overrides, raw=None: [("PLA (Earth Brown)", FORCED[0])]
        )
        assert printer_id is None
        assert "none left in inventory" in reason
        assert all(f.no_stock for fils in holds.values() for f in fils)
        assert holds

    @pytest.mark.asyncio
    async def test_stock_left_is_not_flagged(self, ctx):
        (_, reason), holds = await self._find(
            ctx, PrintScheduler(), lambda pid, overrides, raw=None: [("PLA (Earth Brown)", FORCED[0])], stock=2
        )
        assert "none left" not in reason
        assert holds
        assert not any(f.no_stock for fils in holds.values() for f in fils)

    @pytest.mark.asyncio
    async def test_a_short_only_printer_is_not_flagged_next_to_a_marked_one(self, ctx):
        def pairs(pid, overrides, raw=None):
            return [] if pid == 1 else [("PLA (Earth Brown)", FORCED[0])]

        (_, reason), holds = await self._find(ctx, PrintScheduler(), pairs, short={1})
        assert "none left in inventory" in reason
        assert [f.no_stock for f in holds[1]] == [False]
        assert [f.no_stock for f in holds[2]] == [True]

    @pytest.mark.asyncio
    async def test_a_shared_entry_is_flagged_only_when_no_override_has_stock(self, ctx):
        scheduler = PrintScheduler()
        scheduler._inventory_hints = True
        other = {**FORCED[0], "color": "#112233"}
        overrides = {"PLA (Brown)": [FORCED[0], other]}
        todo = {todo_filament_from_requirement(o) for o in overrides["PLA (Brown)"]}
        out = set()

        async def no_stock(db, t, color, idx):
            return color == "#8B5A2B"

        with patch.object(scheduler, "_no_stock_left", side_effect=no_stock):
            assert await scheduler._mark_out_of_stock(AsyncMock(), ["PLA (Brown)"], overrides, None, out) == [
                "PLA (Brown)"
            ]
        assert out == set()
        with patch.object(scheduler, "_no_stock_left", AsyncMock(return_value=True)):
            await scheduler._mark_out_of_stock(AsyncMock(), ["PLA (Brown)"], overrides, None, out)
        assert out == todo

    @pytest.mark.asyncio
    async def test_the_declined_wake_is_not_flagged(self, ctx):
        from types import SimpleNamespace

        from backend.tests.unit.test_scheduler_loaded_filament_first_3587 import _set

        await _mode(ctx)
        await _set(ctx, "filament_override_inventory", "true")
        item_id = await _add_item(ctx, printer_id=1, age_hours=10)
        scheduler = PrintScheduler()
        plug = SimpleNamespace(
            id=1, name="plug", auto_on=True, enabled=True, printer_id=1, ha_entity_id=None, controls_printer_power=True
        )
        forced = TodoFilament("PLA", "#8B5A2B", "Earth Brown", forced=True)
        patches = [
            patch.object(scheduler, "_get_smart_plugs", AsyncMock(return_value=[plug])),
            patch.object(scheduler, "_power_on_and_wait", AsyncMock(return_value=False)),
            patch.object(scheduler, "_cached_filament_shortfall", MagicMock(return_value=["PLA (Earth Brown)"])),
            patch.object(
                scheduler, "_cached_filament_shortfall_entries", MagicMock(return_value=[("PLA (Earth Brown)", forced)])
            ),
            patch.object(PrintScheduler, "_stock_entries", AsyncMock(return_value=_stock(0))),
        ]
        await _run(ctx, scheduler, connected=lambda pid: pid != 1, extra_patches=patches)

        (hold,) = scheduler.filament_holds_snapshot()[item_id]
        assert [f.no_stock for f in hold.filaments] == [False]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(("first", "flagged"), [(False, True), (True, True)])
    async def test_a_pass_flags_what_the_text_marks(self, ctx, first, flagged):
        from backend.tests.unit.test_scheduler_loaded_filament_first_3587 import _set

        await _mode(ctx, on=first)
        await _set(ctx, "filament_override_inventory", "true")
        overrides = json.dumps(FORCED)
        item_id = await _add_item(ctx, printer_id=1, filament_overrides=overrides, ams_mapping=json.dumps([-1]))
        scheduler = PrintScheduler()
        with patch.object(PrintScheduler, "_stock_entries", AsyncMock(return_value=_stock(0))):
            await _run(ctx, scheduler, real_unmatched=True)

        # Both paths word the wait with the "none left" suffix, so both flag it (#3649:
        # the pinned loaded-filament-first path used to leave it out).
        (hold,) = scheduler.filament_holds_snapshot()[item_id]
        assert [(f.type, f.color_name, f.no_stock) for f in hold.filaments] == [("PLA", "Earth Brown", flagged)]

    @pytest.mark.asyncio
    async def test_the_setting_off_flags_nothing_in_a_pass(self, ctx):
        await _mode(ctx)
        overrides = json.dumps(FORCED)
        item_id = await _add_item(ctx, printer_id=1, filament_overrides=overrides, ams_mapping=json.dumps([-1]))
        scheduler = PrintScheduler()
        with patch.object(PrintScheduler, "_stock_entries", AsyncMock(return_value=_stock(0))):
            await _run(ctx, scheduler, real_unmatched=True)

        (hold,) = scheduler.filament_holds_snapshot()[item_id]
        assert not hold.filaments[0].no_stock


class TestColourNames:
    def test_requirements_take_the_override_colour_name(self):
        scheduler = PrintScheduler()
        item = MagicMock(id=1, filament_overrides=json.dumps(FORCED))
        reqs = [{"slot_id": 1, "type": "PETG", "color": "#000000"}]
        scheduler._apply_filament_overrides(item, reqs)
        assert reqs[0]["color_name"] == "Earth Brown"
        assert reqs[0]["color"] == "#8B5A2B"

    def test_no_override_name_adds_nothing(self):
        scheduler = PrintScheduler()
        override = [{"slot_id": 1, "type": "PLA", "color": "#112233"}]
        item = MagicMock(id=1, filament_overrides=json.dumps(override))
        reqs = [{"slot_id": 1, "type": "PETG", "color": "#000000"}]
        scheduler._apply_filament_overrides(item, reqs)
        assert not reqs[0].get("color_name")  # #3590 writes "" when the override has no name


_ = _BROWN
