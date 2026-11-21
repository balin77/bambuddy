"""A pinned printer waiting for a colour from the inventory (#3649).

The print dialog queues such a job with a forced override for the picked slot
and ``-1`` at that slot of the mapping (the other slots keep their trays). The
scheduler already reads that as "no tray yet": the stored mapping is kept (an
unresolved slot is no conflict), the job waits, and once the colour is loaded
only the gap is filled. These tests pin that behaviour, and the stock hint and
out-of-stock event the pinned filament-first path was missing.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.app.services.inventory_stock import StockEntry
from backend.app.services.print_scheduler import _NO_STOCK_SUFFIX, PrintScheduler
from backend.tests.unit import test_scheduler_loaded_filament_first_3587 as filament_first
from backend.tests.unit.test_scheduler_loaded_filament_first_3587 import ctx  # noqa: F401 - fixture

# Slot 1 prints white, slot 2 the colour the dialog replaces with one from the shelf.
REQUIREMENTS = [
    {"slot_id": 1, "type": "PLA", "color": "#FFFFFF", "tray_info_idx": "GFA00"},
    {"slot_id": 2, "type": "PLA", "color": "#000000", "tray_info_idx": "GFA00"},
]
PICK = {
    "slot_id": 2,
    "type": "PLA",
    "color": "#C0392B",
    "color_name": "Lava Red",
    "tray_info_idx": "GFA00",
    "force_color_match": True,
}

LOADED = [
    {"global_tray_id": 0, "type": "PETG", "color": "000000FF", "tray_info_idx": "GFG00"},
    {"global_tray_id": 1, "type": "PLA", "color": "00FF00FF", "tray_info_idx": "GFA00"},
    {"global_tray_id": 2, "type": "PLA", "color": "FFFFFFFF", "tray_info_idx": "GFA00"},
]
RED_ON_5 = {"global_tray_id": 5, "type": "PLA", "color": "C0392BFF", "tray_info_idx": "GFA00"}

STOCK = "backend.app.services.print_scheduler.PrintScheduler._stock_entries"
NOTIFY = "backend.app.services.notification_service.notification_service.on_filament_out_of_stock"
WAITING = "backend.app.services.print_scheduler.notification_service.on_queue_job_waiting"


def _item(mapping, overrides=(PICK,)):
    item = MagicMock()
    item.id = 91
    item.printer_id = 4
    item.created_by_id = None
    item.archive_id = 460
    item.library_file_id = None
    item.plate_id = None
    item.ams_mapping = json.dumps(mapping)
    item.skip_filament_check = False
    item.filament_overrides = json.dumps(list(overrides))
    item.required_filament_types = None
    item.manual_start = False
    item.filament_short = False
    item.waiting_reason = None
    return item


def _scheduler(trays, requirements=REQUIREMENTS):
    scheduler = PrintScheduler()
    scheduler._build_loaded_filaments = MagicMock(return_value=[dict(t) for t in trays])
    scheduler._get_filament_requirements = AsyncMock(return_value=[dict(r) for r in requirements])
    scheduler._get_bool_setting = AsyncMock(return_value=False)
    scheduler._get_job_name = AsyncMock(return_value="bracket")
    scheduler._get_printer = AsyncMock(return_value=MagicMock(model="A1", name="A1 Mini"))
    scheduler._filament_deficit = AsyncMock(return_value=[])
    return scheduler


def _status():
    return MagicMock(raw_data={"ams": [{"id": 0}]}, ams_filament_backup=None, fila_switch=None)


async def _settle(scheduler, item):
    with patch("backend.app.services.print_scheduler.printer_manager") as pm:
        pm.get_status.return_value = _status()
        conflict = await scheduler._stored_mapping_conflict(AsyncMock(), 4, item, json.loads(item.ams_mapping))
        unmappable = await scheduler._ensure_ams_mapping(AsyncMock(), 4, item)
    return conflict, unmappable


class TestPinnedMappingWithAnInventorySlot:
    @pytest.mark.asyncio
    async def test_the_unresolved_slot_is_no_conflict_and_the_mapping_is_kept(self):
        scheduler = _scheduler(LOADED)
        item = _item([2, -1])

        conflict, unmappable = await _settle(scheduler, item)

        assert conflict is None
        assert unmappable is None
        assert json.loads(item.ams_mapping) == [2, -1]

    @pytest.mark.asyncio
    async def test_the_job_waits_for_the_colour_on_its_printer(self):
        scheduler = _scheduler(LOADED)
        item = _item([2, -1])
        await _settle(scheduler, item)

        with patch("backend.app.services.print_scheduler.printer_manager") as pm:
            pm.get_status.return_value = _status()
            wanted = await scheduler._filament_wait_wanted(AsyncMock(), item)
            blocked = await scheduler._block_on_unmatched_filament(AsyncMock(), item)

        assert wanted == ("PLA Lava Red", [])
        assert blocked is True
        assert item.waiting_reason == "Needs PLA Lava Red"

    @pytest.mark.asyncio
    async def test_once_loaded_only_the_gap_is_filled(self):
        scheduler = _scheduler([*LOADED, RED_ON_5])
        item = _item([2, -1])

        conflict, _ = await _settle(scheduler, item)

        assert conflict is None
        assert json.loads(item.ams_mapping) == [2, 5]
        with patch("backend.app.services.print_scheduler.printer_manager") as pm:
            pm.get_status.return_value = _status()
            assert await scheduler._filament_wait_wanted(AsyncMock(), item) is None

    @pytest.mark.asyncio
    async def test_the_other_colours_keep_their_slot_when_a_loaded_tray_is_moved_by_hand(self):
        """A hand pick for slot 1 (tray 1, green) survives the fill of slot 2."""
        scheduler = _scheduler([*LOADED, RED_ON_5])
        item = _item([1, -1])

        await _settle(scheduler, item)

        assert json.loads(item.ams_mapping) == [1, 5]

    @pytest.mark.asyncio
    async def test_a_loaded_tray_of_the_wrong_colour_never_fills_the_slot(self):
        scheduler = _scheduler([*LOADED, {**RED_ON_5, "color": "E74C3CFF"}])
        item = _item([2, -1])

        await _settle(scheduler, item)

        assert json.loads(item.ams_mapping) == [2, -1]

    @pytest.mark.asyncio
    async def test_without_a_pick_the_slot_is_matched_as_before(self):
        scheduler = _scheduler(LOADED)
        item = _item([2, -1], overrides=())

        await _settle(scheduler, item)

        assert json.loads(item.ams_mapping) == [2, 1]


class TestDualNozzle:
    NOZZLE = [{**r, "nozzle_id": 1 if r["slot_id"] == 2 else 0} for r in REQUIREMENTS]
    ON_RIGHT_NOZZLE = [{**t, "extruder_id": 0} for t in LOADED]

    @pytest.mark.asyncio
    async def test_the_colour_on_the_other_nozzle_does_not_fill_the_slot(self):
        scheduler = _scheduler([*self.ON_RIGHT_NOZZLE, {**RED_ON_5, "extruder_id": 0}], self.NOZZLE)
        item = _item([2, -1])

        await _settle(scheduler, item)

        assert json.loads(item.ams_mapping) == [2, -1]

    @pytest.mark.asyncio
    async def test_the_colour_on_the_slots_nozzle_fills_it_and_the_wait_names_the_nozzle(self):
        scheduler = _scheduler([*self.ON_RIGHT_NOZZLE, {**RED_ON_5, "extruder_id": 1}], self.NOZZLE)
        item = _item([2, -1])
        await _settle(scheduler, item)
        assert json.loads(item.ams_mapping) == [2, 5]

        waiting = _scheduler(self.ON_RIGHT_NOZZLE, self.NOZZLE)
        item = _item([2, -1])
        await _settle(waiting, item)
        with patch("backend.app.services.print_scheduler.printer_manager") as pm:
            pm.get_status.return_value = _status()
            assert await waiting._filament_wait_wanted(AsyncMock(), item) == ("PLA Lava Red (left nozzle)", [])


class TestStockHintOnTheFilamentFirstPath:
    """The pinned wait names a forced colour the inventory has none of, and says so once (#3649)."""

    @staticmethod
    def _entries(count):
        return [StockEntry("PLA", "#C0392B", "GFA00", "", "", None, None, None, count, count * 800.0)]

    @pytest.mark.asyncio
    async def test_a_forced_colour_with_no_stock_gets_the_suffix(self):
        scheduler = _scheduler(LOADED)
        scheduler._inventory_hints = True
        item = _item([2, -1])
        with patch(STOCK, AsyncMock(return_value=self._entries(0))):
            await _settle(scheduler, item)
            with patch("backend.app.services.print_scheduler.printer_manager") as pm:
                pm.get_status.return_value = _status()
                wanted = await scheduler._filament_wait_wanted(AsyncMock(), item)

        assert wanted == (f"PLA Lava Red{_NO_STOCK_SUFFIX}", ["PLA Lava Red"])

    @pytest.mark.asyncio
    async def test_the_wait_also_hands_over_its_filaments_as_data(self):
        """The waiting and the out-of-stock notification get the colour as data, only the latter the empty one (#3641)."""
        for count, stock in ((0, True), (2, False)):
            scheduler = _scheduler(LOADED)
            scheduler._inventory_hints = True
            item = _item([2, -1])
            with (
                patch(STOCK, AsyncMock(return_value=self._entries(count))),
                patch("backend.app.services.print_scheduler.printer_manager") as pm,
            ):
                pm.get_status.return_value = _status()
                wanted, filaments, out_of_stock = await scheduler._filament_wait_found(AsyncMock(), item)

            assert wanted is not None
            assert [(f.type, f.color_name) for f in filaments] == [("PLA", "Lava Red")]
            assert [(f.type, f.color_name) for f in out_of_stock] == ([("PLA", "Lava Red")] if stock else [])

    @pytest.mark.asyncio
    async def test_the_todo_entry_of_the_hold_is_marked_no_stock_only_when_none_is_left(self):
        """Farm: the "To do" list shows the same finding as the text (#3615, #3649)."""
        for hints, count, expected in ((True, 0, True), (True, 2, False), (False, 0, False)):
            scheduler = _scheduler(LOADED)
            scheduler._inventory_hints = hints
            scheduler._pass_holds = {}
            item = _item([2, -1])
            with (
                patch(STOCK, AsyncMock(return_value=self._entries(count))),
                patch("backend.app.services.print_scheduler.printer_manager") as pm,
            ):
                pm.get_status.return_value = _status()
                await scheduler._filament_wait_wanted(AsyncMock(), item)

            (hold,) = scheduler._pass_holds[item.id]
            assert [f.no_stock for f in hold.filaments] == [expected]

    @pytest.mark.asyncio
    async def test_stock_left_or_hints_off_keep_the_text(self):
        for hints, count in ((True, 2), (False, 0)):
            scheduler = _scheduler(LOADED)
            scheduler._inventory_hints = hints
            item = _item([2, -1])
            with (
                patch(STOCK, AsyncMock(return_value=self._entries(count))),
                patch("backend.app.services.print_scheduler.printer_manager") as pm,
            ):
                pm.get_status.return_value = _status()
                wanted = await scheduler._filament_wait_wanted(AsyncMock(), item)
            assert wanted == ("PLA Lava Red", [])

    @pytest.mark.asyncio
    async def test_the_event_fires_once_when_the_suffix_is_new(self):
        scheduler = _scheduler(LOADED)
        with patch(NOTIFY, AsyncMock()) as notify:
            item = _item([2, -1])
            await scheduler._notify_out_of_stock_once(
                AsyncMock(), item, "Waiting for filament: PLA Lava Red", ["PLA Lava Red"], 4, "A1"
            )
            notify.assert_awaited_once()
            assert notify.await_args.kwargs["filament"] == "PLA Lava Red"
            assert notify.await_args.kwargs["printer_id"] == 4

            notify.reset_mock()
            await scheduler._notify_out_of_stock_once(
                AsyncMock(),
                item,
                f"Waiting for filament: PLA Lava Red{_NO_STOCK_SUFFIX}",
                ["PLA Lava Red"],
                4,
                "A1",
            )
            await scheduler._notify_out_of_stock_once(AsyncMock(), item, None, [], 4, "A1")
            notify.assert_not_awaited()


class TestQueuePassWithLoadedFilamentFirst:
    """A pinned job skipped for filament says when the colour is out of stock, and tells once (#3649)."""

    @staticmethod
    def _pass_patches(scheduler, count, notify):
        entries = [StockEntry("PLA", "#C0392B", "GFA00", "", "", None, None, None, count, count * 800.0)]
        return (patch(STOCK, AsyncMock(return_value=entries)), patch(NOTIFY, notify))

    async def _job(self, ctx):
        await filament_first._mode(ctx, hours="None")
        await filament_first._set(ctx, "filament_override_inventory", "true")
        return await filament_first._add_item(
            ctx, printer_id=1, filament_overrides=json.dumps([PICK]), ams_mapping=json.dumps([-1])
        )

    @pytest.mark.asyncio
    async def test_the_reason_names_the_shortage_and_the_event_fires_once(self, ctx):
        item_id = await self._job(ctx)
        scheduler = PrintScheduler()
        notify = AsyncMock()
        for _ in range(2):
            await filament_first._run(
                ctx, scheduler, real_unmatched=True, extra_patches=self._pass_patches(scheduler, 0, notify)
            )
            reason = (await filament_first._get(ctx, item_id)).waiting_reason
            assert reason == f"Waiting for filament: PLA Lava Red{_NO_STOCK_SUFFIX}"
        notify.assert_awaited_once()
        assert notify.await_args.kwargs["filament"] == "PLA Lava Red"
        assert notify.await_args.kwargs["printer_id"] == 1

    @pytest.mark.asyncio
    async def test_stock_left_keeps_the_reason_and_sends_nothing(self, ctx):
        item_id = await self._job(ctx)
        scheduler = PrintScheduler()
        notify = AsyncMock()
        await filament_first._run(
            ctx, scheduler, real_unmatched=True, extra_patches=self._pass_patches(scheduler, 2, notify)
        )
        assert (await filament_first._get(ctx, item_id)).waiting_reason == "Waiting for filament: PLA Lava Red"
        notify.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_busy_hold_in_between_does_not_tell_again(self, ctx):
        """The held reason is replaced by "Busy: ..." while another job prints; the same shortage is not new then."""
        item_id = await self._job(ctx)
        scheduler = PrintScheduler()
        notify = AsyncMock()
        for idle in (True, False, True, False, True):
            await filament_first._run(
                ctx,
                scheduler,
                real_unmatched=True,
                idle=lambda pid, idle=idle: idle,
                extra_patches=self._pass_patches(scheduler, 0, notify),
            )
        reason = (await filament_first._get(ctx, item_id)).waiting_reason
        assert reason == f"Waiting for filament: PLA Lava Red{_NO_STOCK_SUFFIX}"
        notify.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stock_refilled_and_gone_again_is_told_again(self, ctx):
        await self._job(ctx)
        scheduler = PrintScheduler()
        notify = AsyncMock()
        for count in (0, 0, 2, 2, 0, 0):
            await filament_first._run(
                ctx, scheduler, real_unmatched=True, extra_patches=self._pass_patches(scheduler, count, notify)
            )
        assert notify.await_count == 2

    @pytest.mark.asyncio
    async def test_a_job_that_left_the_queue_is_forgotten(self, ctx):
        item_id = await self._job(ctx)
        scheduler = PrintScheduler()
        notify = AsyncMock()
        await filament_first._run(
            ctx, scheduler, real_unmatched=True, extra_patches=self._pass_patches(scheduler, 0, notify)
        )
        assert item_id in scheduler._out_of_stock_notified

        async with ctx.session_maker() as db:
            (await db.get(filament_first.PrintQueueItem, item_id)).status = "cancelled"
            await db.commit()
        await filament_first._run(ctx, scheduler)

        assert scheduler._out_of_stock_notified == {}


class TestSwitchedOffPrinterDeclinesTheWake:
    """A pinned job whose switched-off printer cannot supply the colour says so the same way (#3649)."""

    @pytest.mark.asyncio
    async def test_the_reason_carries_the_suffix_and_the_event_fires_once(self, ctx):
        await filament_first._mode(ctx, hours="None")
        await filament_first._set(ctx, "filament_override_inventory", "true")
        item_id = await filament_first._add_item(
            ctx, printer_id=1, filament_overrides=json.dumps([PICK]), ams_mapping=json.dumps([-1])
        )
        scheduler = PrintScheduler()
        notify = AsyncMock()
        reading = {"ams": [{"tray": [{"tray_type": "PLA", "tray_color": "00FF00FF", "tray_info_idx": "GFA00"}]}]}
        entries = [StockEntry("PLA", "#C0392B", "GFA00", "", "", None, None, None, 0, 0.0)]
        plug = MagicMock(id=1, name="plug", auto_on=True, enabled=True, printer_id=1, controls_printer_power=True)
        power_on = AsyncMock(return_value=False)
        for _ in range(2):
            await filament_first._run(
                ctx,
                scheduler,
                connected=lambda pid: pid != 1,
                extra_patches=[
                    patch.object(scheduler, "_get_smart_plugs", AsyncMock(return_value=[plug])),
                    patch.object(scheduler, "_power_on_and_wait", power_on),
                    patch.object(scheduler, "_tray_reading", MagicMock(return_value=reading)),
                    patch(STOCK, AsyncMock(return_value=entries)),
                    patch(NOTIFY, notify),
                ],
            )

        power_on.assert_not_awaited()
        reason = (await filament_first._get(ctx, item_id)).waiting_reason
        assert reason.startswith("Waiting for filament: ")
        assert reason.endswith(_NO_STOCK_SUFFIX)
        notify.assert_awaited_once()
        assert notify.await_args.kwargs["printer_id"] == 1


class TestModelPathRace:
    """The matcher let a printer through but the filament check at dispatch disagrees (#3649)."""

    @pytest.mark.asyncio
    async def test_the_released_job_says_none_left_and_tells_once(self, ctx):
        await filament_first._mode(ctx, hours="None")
        await filament_first._set(ctx, "filament_override_inventory", "true")
        item_id = await filament_first._add_item(ctx)
        scheduler = PrintScheduler()
        notify = AsyncMock()
        entries = [StockEntry("PLA", "#C0392B", "GFA00", "", "", None, None, None, 0, 0.0)]
        for _ in range(2):
            await filament_first._run(
                ctx,
                scheduler,
                extra_patches=[
                    patch.object(scheduler, "_unmatched_requirements", AsyncMock(return_value=[dict(PICK)])),
                    patch(STOCK, AsyncMock(return_value=entries)),
                    patch(NOTIFY, notify),
                ],
            )

        item = await filament_first._get(ctx, item_id)
        assert item.printer_id is None
        assert item.waiting_reason == f"Waiting for filament: PLA Lava Red{_NO_STOCK_SUFFIX}"
        notify.assert_awaited_once()
        assert notify.await_args.kwargs["filament"] == "PLA Lava Red"
