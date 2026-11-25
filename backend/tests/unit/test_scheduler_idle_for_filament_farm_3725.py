"""The idle-for-filament event on the farm branch reads the "To do" holds (#3725).

The scheduler's own record of what a job waits for (``_record_hold``, which the
"To do" list and the waiting notices read as well) is what a printer standing idle
is told to load. Same harness as ``test_scheduler_idle_for_filament_3725``.
"""

from unittest.mock import AsyncMock, patch

import pytest

from backend.app.services.print_scheduler import PrintScheduler
from backend.app.services.queue_todo import ShortTray, TodoFilament
from backend.tests.unit.test_scheduler_idle_for_filament_3725 import (
    DEFICIT,
    PETG_ONLY,
    PETG_TRAYS,
    PLA_TRAYS,
    _set_setting,
    add_item,
    add_plug,
    announced_printers,
    at,
    ctx,  # noqa: F401 - fixture
    new_scheduler,
    off,
    one_pass,
    pass_pair,
)

RED = [{"slot_id": 1, "type": "PLA", "color": "#C12E1F", "color_name": "Lava Red"}]
SHORT_RED = TodoFilament(
    "PLA",
    "#C12E1F",
    "Lava Red",
    short=True,
    short_trays=(ShortTray(0, 2, 196.0),),
    required_grams=505.0,
)


class TestCollector:
    def test_a_hold_feeds_the_collector_per_printer_and_job(self):
        scheduler = PrintScheduler()
        scheduler._pass_filament_blocks = {}

        scheduler._record_hold(7, 1, "P1S", [SHORT_RED])
        scheduler._record_hold(7, 1, "P1S", [SHORT_RED])
        scheduler._record_hold(8, 2, None, [TodoFilament("PETG", "#000000")])

        assert scheduler._pass_filament_blocks == {1: {7: [SHORT_RED]}, 2: {8: [TodoFilament("PETG", "#000000")]}}

    def test_model_holds_are_recorded_for_each_printer_that_lacks_something(self):
        scheduler = PrintScheduler()
        scheduler._pass_filament_blocks = {}

        scheduler._record_model_holds(
            7, {1: ("P1S", [SHORT_RED]), 2: ("P1S", [TodoFilament("PLA", "#7D6556", "Army Beige")])}
        )

        assert set(scheduler._pass_filament_blocks) == {1, 2}

    def test_a_hold_without_a_printer_is_no_printers(self):
        scheduler = PrintScheduler()
        scheduler._pass_filament_blocks = {}

        scheduler._record_hold(7, None, "P1S", [SHORT_RED])

        assert scheduler._pass_filament_blocks == {}

    def test_a_hold_without_filaments_records_nothing(self):
        scheduler = PrintScheduler()
        scheduler._pass_filament_blocks = {}

        scheduler._record_hold(7, 1, "P1S", [])

        assert scheduler._pass_filament_blocks == {}


class TestFarmWording:
    @pytest.mark.asyncio
    async def test_the_load_line_names_the_colour_and_the_slot_amounts(self, ctx):  # noqa: F811
        scheduler = new_scheduler(ctx)
        item = await add_item(ctx, "Lamp_Base", printer_id=1)
        await one_pass(ctx, scheduler, deficits={item: DEFICIT}, unmatched={})
        at(ctx, 300)

        due = await one_pass(ctx, scheduler, deficits={item: DEFICIT})

        (need,) = due.event.await_args.args[2][0].needs
        assert need.line.endswith("PLA (A3 has 196 g, needs 505 g)")

    @pytest.mark.asyncio
    async def test_a_forced_colour_to_load_has_the_colour_name_and_no_amounts(self, ctx):  # noqa: F811
        scheduler = new_scheduler(ctx)
        item = await add_item(ctx, "Coaster", printer_id=1)
        await one_pass(ctx, scheduler, unmatched={item: RED})
        at(ctx, 300)

        due = await one_pass(ctx, scheduler, unmatched={item: RED})

        (need,) = due.event.await_args.args[2][0].needs
        assert "Lava Red" in need.line
        assert "(" not in need.line.replace("(#", "")

    def test_the_short_load_line_is_the_to_do_sentence_without_the_job(self):
        needs = PrintScheduler._filament_needs([SHORT_RED], None)

        assert needs[0].line.endswith("PLA Lava Red (A3 has 196 g, needs 505 g)")

    def test_a_pool_of_spools_is_summed_and_said_in_the_plural(self):
        pool = TodoFilament(
            "PLA",
            "#C12E1F",
            "Lava Red",
            short=True,
            short_trays=(ShortTray(0, 1, 10.0), ShortTray(0, 2, 15.0)),
            required_grams=505.0,
        )

        (need,) = PrintScheduler._filament_needs([pool], None)

        assert need.line.endswith("PLA Lava Red (A2 + A3 have 25 g, needs 505 g)")

    def test_a_spool_whose_amount_is_unknown_is_named_without_grams(self):
        unknown = TodoFilament(
            "PLA", "#C12E1F", "Lava Red", short=True, short_trays=(ShortTray(0, 2, None),), required_grams=505.0
        )

        (need,) = PrintScheduler._filament_needs([unknown], None)

        assert need.have_grams is None
        assert "196" not in need.line


class TestPlateChanger:
    @pytest.mark.asyncio
    async def test_an_empty_plate_changer_is_not_told_even_with_a_hold(self, ctx):  # noqa: F811
        """The queue holds a job for the empty changer before any filament hold; a carried one must not count."""
        scheduler = new_scheduler(ctx)
        item = await add_item(ctx, "Lamp_Base", printer_id=1)
        sent = AsyncMock()

        async def check(empty):
            scheduler._plate_changer_empty = empty
            scheduler._pass_filament_blocks = {}
            scheduler._record_hold(item, 1, "P1S", [SHORT_RED])
            async with ctx.session_maker() as db:
                with (
                    patch("backend.app.services.print_scheduler.printer_manager.is_connected", return_value=True),
                    patch.object(scheduler, "_is_printer_idle", return_value=True),
                    patch(
                        "backend.app.services.notification_service.notification_service.on_printer_idle_for_filament",
                        sent,
                    ),
                ):
                    await scheduler._check_filament_idle(db, set(), True)

        await check({1: "P1S right"})
        at(ctx, 600)
        await check({1: "P1S right"})
        sent.assert_not_awaited()

        await check({})
        at(ctx, 1300)
        await check({})
        sent.assert_awaited_once()


class TestSwitchedOffPrintersThroughTheHolds:
    """A switched-off printer reaches the event through the holds the "To do" list reads (#3725)."""

    @pytest.mark.asyncio
    async def test_a_pinned_job_hold_on_an_off_printer_fires(self, ctx):  # noqa: F811
        await add_plug(ctx, 1)
        await add_item(ctx, "Lamp", printer_id=1, required_filament_types=PETG_ONLY)

        due = await pass_pair(ctx, new_scheduler(ctx), **off(1), trays={1: PLA_TRAYS})

        assert announced_printers(due) == [1]

    @pytest.mark.asyncio
    async def test_a_model_job_hold_on_an_off_printer_fires(self, ctx):  # noqa: F811
        await add_plug(ctx, 1)
        await add_item(ctx, "Lamp", target_model="P1S", required_filament_types=PETG_ONLY)

        due = await pass_pair(ctx, new_scheduler(ctx), **off(1), trays={1: PLA_TRAYS})

        assert 1 in announced_printers(due)

    @pytest.mark.asyncio
    async def test_a_fitting_off_printer_means_the_other_one_is_not_waiting(self, ctx):  # noqa: F811
        """Printer 2 was last loaded with PETG: the job goes there once it is switched on, printer 1 waits for nothing."""
        await add_plug(ctx, 1)
        await add_plug(ctx, 2)
        scheduler = new_scheduler(ctx)
        await add_item(ctx, "Lamp", target_model="P1S", required_filament_types=PETG_ONLY)
        extra = (patch.object(scheduler, "_wake_printer_for_model", AsyncMock(return_value=(None, None))),)

        due = await pass_pair(ctx, scheduler, **off(1, 2), trays={1: PLA_TRAYS, 2: PETG_TRAYS}, extra=extra)

        due.event.assert_not_awaited()
        assert 1 in scheduler._pass_filament_blocks  # the To do list keeps the hold

    @pytest.mark.asyncio
    @pytest.mark.parametrize("kind", ["pinned", "model"])
    async def test_nothing_for_an_off_printer_without_loaded_filament_first(self, ctx, kind):  # noqa: F811
        await _set_setting(ctx, "queue_loaded_filament_first", "false")
        await add_plug(ctx, 1)
        fields = {"printer_id": 1} if kind == "pinned" else {"target_model": "P1S"}
        await add_item(ctx, "Lamp", required_filament_types=PETG_ONLY, **fields)

        due = await pass_pair(ctx, new_scheduler(ctx), **off(1), trays={1: PLA_TRAYS})

        due.event.assert_not_awaited()
