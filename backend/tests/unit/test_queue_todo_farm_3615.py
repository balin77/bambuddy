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
from backend.app.services.queue_todo import FilamentHold, TodoFilament, priority_state
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
    return [StockEntry("PLA", "#8B5A2B", "", "", "", None, None, None, count, 0.0, 0)]


class TestNoStockFlags:
    """#3590: only with the setting on, only forced colours, only known zero stock."""

    def _holds(self):
        forced = TodoFilament("PLA", "#8B5A2B", "Earth Brown", forced=True)
        loose = TodoFilament("PLA", "#8B5A2B", "Earth Brown", forced=False)
        return {1: [FilamentHold(1, 1, None, (forced,))], 2: [FilamentHold(2, 1, None, (loose,))]}

    @pytest.mark.asyncio
    async def test_a_forced_colour_with_zero_stock_is_flagged(self, ctx):
        scheduler = PrintScheduler()
        scheduler._inventory_hints = True
        holds = self._holds()
        with (
            patch("backend.app.services.print_scheduler.async_session", ctx.session_maker),
            patch.object(scheduler, "_stock_entries", AsyncMock(return_value=_stock(0))),
        ):
            await scheduler._flag_holds_without_stock(holds)
        assert holds[1][0].filaments[0].no_stock is True
        # Not forced: the text never says it either.
        assert holds[2][0].filaments[0].no_stock is False

    @pytest.mark.asyncio
    @pytest.mark.parametrize("stock", [_stock(2), None, []])
    async def test_stock_left_or_unknown_is_not_flagged(self, ctx, stock):
        scheduler = PrintScheduler()
        scheduler._inventory_hints = True
        holds = self._holds()
        with (
            patch("backend.app.services.print_scheduler.async_session", ctx.session_maker),
            patch.object(scheduler, "_stock_entries", AsyncMock(return_value=stock)),
        ):
            await scheduler._flag_holds_without_stock(holds)
        assert not any(f.no_stock for hs in holds.values() for h in hs for f in h.filaments)

    @pytest.mark.asyncio
    async def test_with_the_setting_off_the_inventory_is_never_read(self, ctx):
        scheduler = PrintScheduler()
        scheduler._inventory_hints = False
        holds = self._holds()
        entries = AsyncMock(return_value=_stock(0))
        with patch.object(scheduler, "_stock_entries", entries):
            await scheduler._flag_holds_without_stock(holds)
        entries.assert_not_awaited()
        assert not any(f.no_stock for hs in holds.values() for h in hs for f in h.filaments)

    @pytest.mark.asyncio
    async def test_a_failing_lookup_leaves_the_holds_alone(self, ctx):
        scheduler = PrintScheduler()
        scheduler._inventory_hints = True
        holds = self._holds()
        with (
            patch("backend.app.services.print_scheduler.async_session", ctx.session_maker),
            patch.object(scheduler, "_no_stock_left", AsyncMock(side_effect=RuntimeError("boom"))),
        ):
            await scheduler._flag_holds_without_stock(holds)
        assert not any(f.no_stock for hs in holds.values() for h in hs for f in h.filaments)

    @pytest.mark.asyncio
    async def test_a_pass_flags_the_published_snapshot(self, ctx):
        from backend.tests.unit.test_scheduler_loaded_filament_first_3587 import _set

        await _mode(ctx)
        await _set(ctx, "filament_override_inventory", "true")
        overrides = json.dumps(FORCED)
        item_id = await _add_item(ctx, printer_id=1, filament_overrides=overrides, ams_mapping=json.dumps([-1]))
        scheduler = PrintScheduler()
        with patch.object(PrintScheduler, "_stock_entries", AsyncMock(return_value=_stock(0))):
            await _run(ctx, scheduler, real_unmatched=True)

        (hold,) = scheduler.filament_holds_snapshot()[item_id]
        assert [(f.type, f.color_name, f.no_stock) for f in hold.filaments] == [("PLA", "Earth Brown", True)]

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
        assert "color_name" not in reqs[0]


_ = _BROWN
