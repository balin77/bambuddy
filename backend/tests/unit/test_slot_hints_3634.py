"""Which slot a missing filament can go into (#3634)."""

import json
from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import delete

from backend.app.core.printer_scope import PrinterScope
from backend.app.models.print_queue import PrintQueueItem
from backend.app.services.bambu_mqtt import FilaSwitchState, PrinterState
from backend.app.services.print_scheduler import PrintScheduler
from backend.app.services.queue_todo import (
    HINT_ALL_NEEDED,
    HINT_FREE,
    HINT_REPLACEABLE,
    FilamentHold,
    TodoFilament,
)
from backend.tests.unit.test_ams_mapping_per_printer_2799 import (
    P2S_4_TRAYS,
    P2S_5_TRAYS,
    SHARED_MAPPING,
    _item,
    _scheduler,
)
from backend.tests.unit.test_scheduler_model_filament_short_3137 import (
    _add_item,
    queue_db,  # noqa: F401 - fixture
)


def _planning_scheduler(trays, requirements=None):
    scheduler = _scheduler(trays) if requirements is None else _scheduler(trays, requirements)
    scheduler._get_bool_setting = AsyncMock(return_value=False)
    scheduler._creator_filament_scope = AsyncMock(return_value=MagicMock(is_unrestricted=True))
    return scheduler


class TestPlannedMapping:
    """``_planned_mapping`` is what ``missing_filament_for_start`` reads: no new behaviour."""

    @pytest.mark.asyncio
    async def test_a_stored_mapping_that_fits_is_kept(self):
        scheduler = _scheduler(P2S_4_TRAYS)
        with patch("backend.app.services.print_scheduler.printer_manager") as pm:
            pm.get_status.return_value = MagicMock()
            mapping = await scheduler._planned_mapping(AsyncMock(), _item(), 9)
        assert mapping == SHARED_MAPPING

    @pytest.mark.asyncio
    async def test_a_stored_mapping_that_conflicts_is_matched_afresh(self):
        # The mapping was resolved on another printer: here slot 3 would get ASA.
        scheduler = _planning_scheduler(P2S_5_TRAYS)
        with patch("backend.app.services.print_scheduler.printer_manager") as pm:
            pm.get_status.return_value = MagicMock()
            mapping = await scheduler._planned_mapping(AsyncMock(), _item(), 8)
        assert mapping[0] == 0
        assert mapping[2] == 2

    @pytest.mark.asyncio
    async def test_no_stored_mapping_is_matched(self):
        scheduler = _planning_scheduler(P2S_5_TRAYS)
        with patch("backend.app.services.print_scheduler.printer_manager") as pm:
            pm.get_status.return_value = MagicMock()
            mapping = await scheduler._planned_mapping(AsyncMock(), _item(ams_mapping=None), 8)
        assert (mapping[0], mapping[2]) == (0, 2)

    @pytest.mark.asyncio
    async def test_an_unreadable_stored_mapping_is_matched_and_nothing_to_match_is_empty(self):
        scheduler = _planning_scheduler(P2S_5_TRAYS, requirements=[])
        with patch("backend.app.services.print_scheduler.printer_manager") as pm:
            pm.get_status.return_value = MagicMock()
            mapping = await scheduler._planned_mapping(AsyncMock(), _item(ams_mapping="not json"), 8)
        assert mapping == []

    @pytest.mark.asyncio
    async def test_the_pass_memos_are_left_alone(self):
        scheduler = _scheduler(P2S_5_TRAYS)
        scheduler._filament_req_memo[("kept",)] = [{"slot_id": 1}]
        with patch("backend.app.services.print_scheduler.printer_manager") as pm:
            pm.get_status.return_value = MagicMock()
            await scheduler._planned_mapping(AsyncMock(), _item(ams_mapping=json.dumps([0, -1, 2])), 8)
        assert scheduler._filament_req_memo[("kept",)] == [{"slot_id": 1}]


# ---------------------------------------------------------------------------
# The pass step: where can the missing filament go?
# ---------------------------------------------------------------------------

RED, BLUE, WHITE, GREEN = "FF0000", "0000FF", "FFFFFF", "00FF00"
PINK = TodoFilament("PLA", "#FF69B4", "Pink")


def _tray(slot, material="", color="", **extra):
    tray = {"id": slot, "tray_type": material, "tray_color": color + "FF" if color else "", "tray_info_idx": ""}
    tray.update(extra)
    return tray


def _loaded_ams(*colors):
    return [{"id": 0, "tray": [_tray(i, "PLA", c) for i, c in enumerate(colors)]}]


def _status(ams=None, vt=None, state="IDLE", **fields):
    status = PrinterState(connected=True, state=state)
    status.raw_data = {"ams": ams if ams is not None else [], "vt_tray": vt or []}
    for key, value in fields.items():
        setattr(status, key, value)
    return status


def _job(item_id, printer_id=1, **fields):
    item = MagicMock()
    item.id = item_id
    item.printer_id = printer_id
    item.target_model = None
    item.target_location = None
    item.variants = []
    item.created_by_id = None
    item.ams_mapping = None
    item.skip_filament_check = False
    item.filament_overrides = None
    item.status = "pending"
    item.archive_id = item_id
    item.library_file_id = None
    item.plate_id = None
    for key, value in fields.items():
        setattr(item, key, value)
    return item


def _need(*colors):
    """The requirements of a job that prints in each of ``colors`` (PLA)."""
    return [{"slot_id": i + 1, "type": "PLA", "color": "#" + c, "tray_info_idx": ""} for i, c in enumerate(colors)]


def _scheduler_with(requirements: dict):
    """A scheduler whose jobs have the given requirements, by item id (None: unreadable file)."""
    scheduler = PrintScheduler()
    scheduler._get_filament_requirements = AsyncMock(
        side_effect=lambda db, item: [dict(r) for r in requirements[item.id]] if requirements.get(item.id) else None
    )
    scheduler._get_bool_setting = AsyncMock(return_value=False)
    scheduler._creator_filament_scope = AsyncMock(return_value=MagicMock(is_unrestricted=True))
    return scheduler


def _holds(*printer_ids, filaments=(PINK,)):
    return {100 + pid: [FilamentHold(100 + pid, pid, None, tuple(filaments))] for pid in printer_ids}


async def _hints(scheduler, statuses, items, holds, db=None, connected=lambda pid: True):
    with (
        patch(
            "backend.app.services.print_scheduler.printer_manager.get_status",
            MagicMock(side_effect=lambda pid: statuses.get(pid)),
        ),
        patch(
            "backend.app.services.print_scheduler.printer_manager.is_connected",
            MagicMock(side_effect=connected),
        ),
    ):
        hints, memo = await scheduler._compute_slot_hints(db or AsyncMock(), items, holds)
    # What the pass does once the hint step went through.
    scheduler._hint_memo = memo
    return hints


def _labels(hint):
    return [(s.ams_id, s.tray_id, s.type, s.color) for s in hint.slots]


class TestSlotHint:
    @pytest.mark.asyncio
    async def test_a_free_slot_is_named(self):
        ams = [{"id": 0, "tray": [_tray(0, "PLA", RED), _tray(1, exists=False), _tray(2, "PLA", WHITE), _tray(3)]}]
        ams[0]["tray"][3]["exists"] = False
        held = _job(1)
        scheduler = _scheduler_with({1: _need(RED, "FF69B4")})
        hints = await _hints(scheduler, {1: _status(ams)}, [held], _holds(1))
        assert hints[1].state == HINT_FREE
        assert [(s.ams_id, s.tray_id, s.type) for s in hints[1].slots] == [(0, 1, ""), (0, 3, "")]
        assert hints[1].unknown_jobs == 0

    @pytest.mark.asyncio
    async def test_a_slot_without_a_presence_bit_is_free_on_the_firmware_state(self):
        ams = [{"id": 0, "tray": [_tray(0, "PLA", RED), _tray(1, state=10), _tray(2, "PLA", WHITE), _tray(3, state=3)]}]
        scheduler = _scheduler_with({1: _need(RED)})
        hints = await _hints(scheduler, {1: _status(ams)}, [_job(1)], _holds(1))
        # Slot 4 reads like a spool the printer cannot identify: not offered.
        assert [(s.tray_id) for s in hints[1].slots] == [1]

    @pytest.mark.asyncio
    async def test_a_spool_the_printer_cannot_identify_is_not_a_free_slot(self):
        ams = [{"id": 0, "tray": [_tray(0, "PLA", RED), _tray(1, exists=True)]}]
        scheduler = _scheduler_with({1: _need(RED)})
        hints = await _hints(scheduler, {1: _status(ams)}, [_job(1)], _holds(1))
        assert hints[1].state == HINT_ALL_NEEDED

    @pytest.mark.asyncio
    async def test_slots_no_waiting_job_needs_can_be_replaced(self):
        ams = _loaded_ams(RED, BLUE, WHITE, GREEN)
        # The held job needs red; another job waits for blue and white.
        scheduler = _scheduler_with({1: _need(RED), 2: _need(BLUE, WHITE)})
        hints = await _hints(scheduler, {1: _status(ams)}, [_job(1), _job(2)], _holds(1))
        assert hints[1].state == HINT_REPLACEABLE
        assert _labels(hints[1]) == [(0, 3, "PLA", "#00FF00")]

    @pytest.mark.asyncio
    async def test_every_loaded_filament_needed(self):
        ams = _loaded_ams(RED, BLUE, WHITE, GREEN)
        scheduler = _scheduler_with({1: _need(RED, BLUE), 2: _need(WHITE, GREEN)})
        hints = await _hints(scheduler, {1: _status(ams)}, [_job(1), _job(2)], _holds(1))
        assert (hints[1].state, hints[1].slots) == (HINT_ALL_NEEDED, ())

    @pytest.mark.asyncio
    async def test_the_job_staged_or_scheduled_still_needs_its_trays(self):
        ams = _loaded_ams(RED, BLUE)
        staged = _job(2, manual_start=True)
        later = _job(3, scheduled_time="2099-01-01")
        scheduler = _scheduler_with({1: _need(RED), 2: _need(BLUE), 3: _need(RED)})
        hints = await _hints(scheduler, {1: _status(ams)}, [_job(1), staged, later], _holds(1))
        assert hints[1].state == HINT_ALL_NEEDED

    @pytest.mark.asyncio
    async def test_a_job_pinned_to_another_printer_claims_nothing_here(self):
        ams = _loaded_ams(RED, BLUE)
        scheduler = _scheduler_with({1: _need(RED), 2: _need(BLUE)})
        hints = await _hints(scheduler, {1: _status(ams)}, [_job(1), _job(2, printer_id=2)], _holds(1))
        assert _labels(hints[1]) == [(0, 1, "PLA", "#0000FF")]

    @pytest.mark.asyncio
    async def test_the_running_print_s_trays_are_never_offered(self):
        ams = _loaded_ams(RED, BLUE, WHITE)
        running = _status(ams, state="RUNNING", print_ams_mapping=[2], tray_now=2)
        scheduler = _scheduler_with({1: _need(RED)})
        hints = await _hints(scheduler, {1: running}, [_job(1)], _holds(1))
        assert [s.tray_id for s in hints[1].slots] == [1]

    @pytest.mark.asyncio
    async def test_the_tray_the_extruder_holds_is_never_offered(self):
        from backend.app.services.bambu_mqtt import ExtruderSlot

        ams = _loaded_ams(RED, BLUE)
        running = _status(ams, state="PAUSE", extruder_slots={0: ExtruderSlot(ams_id=0, slot_id=1, has_filament=True)})
        scheduler = _scheduler_with({1: _need(RED)})
        hints = await _hints(scheduler, {1: running}, [_job(1)], _holds(1))
        assert hints[1].state == HINT_ALL_NEEDED

    @pytest.mark.asyncio
    async def test_an_idle_printer_s_old_mapping_is_not_a_running_print(self):
        ams = _loaded_ams(RED, BLUE, WHITE)
        idle = _status(ams, state="FINISH", print_ams_mapping=[2], tray_now=2)
        scheduler = _scheduler_with({1: _need(RED)})
        hints = await _hints(scheduler, {1: idle}, [_job(1)], _holds(1))
        assert [s.tray_id for s in hints[1].slots] == [1, 2]

    @pytest.mark.asyncio
    async def test_a_printer_that_reported_no_trays_has_no_hint(self):
        scheduler = _scheduler_with({1: _need(RED)})
        for statuses in ({}, {1: _status(ams=[], vt=[])}):
            assert await _hints(scheduler, statuses, [_job(1)], _holds(1)) == {}

    @pytest.mark.asyncio
    async def test_an_offline_printer_has_no_hint(self):
        scheduler = _scheduler_with({1: _need(RED)})
        hints = await _hints(
            scheduler, {1: _status(_loaded_ams(RED, BLUE))}, [_job(1)], _holds(1), connected=lambda pid: False
        )
        assert hints == {}

    @pytest.mark.asyncio
    async def test_a_job_whose_filaments_are_unknown_is_counted_and_claims_nothing(self):
        ams = _loaded_ams(RED, BLUE)
        scheduler = _scheduler_with({1: _need(RED), 2: None, 3: None})
        hints = await _hints(scheduler, {1: _status(ams)}, [_job(1), _job(2), _job(3, printer_id=2)], _holds(1))
        assert hints[1].unknown_jobs == 1
        assert _labels(hints[1]) == [(0, 1, "PLA", "#0000FF")]

    @pytest.mark.asyncio
    async def test_a_forced_override_claims_its_tray_when_the_file_is_unreadable(self):
        ams = _loaded_ams(RED, BLUE)
        forced = _job(
            2,
            filament_overrides=json.dumps(
                [{"slot_id": 1, "type": "PLA", "color": "#0000FF", "force_color_match": True}]
            ),
        )
        scheduler = _scheduler_with({1: _need(RED), 2: None})
        hints = await _hints(scheduler, {1: _status(ams)}, [_job(1), forced], _holds(1))
        assert hints[1].state == HINT_ALL_NEEDED
        assert hints[1].unknown_jobs == 0

    @pytest.mark.asyncio
    async def test_a_job_that_cannot_be_read_does_not_hide_the_hint(self):
        ams = _loaded_ams(RED, BLUE)
        scheduler = _scheduler_with({1: _need(RED), 2: _need(BLUE)})
        scheduler._planned_mapping = AsyncMock(side_effect=[[0], RuntimeError("bad 3mf")])
        hints = await _hints(scheduler, {1: _status(ams)}, [_job(1), _job(2)], _holds(1))
        assert hints[1].unknown_jobs == 1
        assert [s.tray_id for s in hints[1].slots] == [1]

    @pytest.mark.asyncio
    async def test_only_printers_with_a_filament_hold_get_a_hint(self):
        ams = _loaded_ams(RED, BLUE)
        scheduler = _scheduler_with({1: _need(RED)})
        statuses = {1: _status(ams), 2: _status(ams)}
        assert set(await _hints(scheduler, statuses, [_job(1)], _holds(1))) == {1}
        assert await _hints(scheduler, statuses, [_job(1)], {}) == {}


class TestExternalHolder:
    @pytest.mark.asyncio
    async def test_it_is_offered_when_the_printer_has_no_ams_slot(self):
        vt = [{"id": 254, "tray_type": "PETG", "tray_color": "00FF00FF", "tray_info_idx": ""}]
        scheduler = _scheduler_with({1: _need(RED)})
        hints = await _hints(scheduler, {1: _status(vt=vt)}, [_job(1)], _holds(1))
        assert hints[1].state == HINT_REPLACEABLE
        assert [(s.is_external, s.type) for s in hints[1].slots] == [(True, "PETG")]

    @pytest.mark.asyncio
    async def test_it_is_not_offered_next_to_ams_slots(self):
        vt = [{"id": 254, "tray_type": "PLA", "tray_color": "00FF00FF", "tray_info_idx": ""}]
        ams = _loaded_ams(RED, BLUE)
        scheduler = _scheduler_with({1: _need(RED, BLUE)})
        hints = await _hints(scheduler, {1: _status(ams, vt=vt)}, [_job(1)], _holds(1))
        assert (hints[1].state, hints[1].slots) == (HINT_ALL_NEEDED, ())

    @pytest.mark.asyncio
    async def test_it_is_never_called_free(self):
        vt = [{"id": 254, "tray_type": "", "tray_color": "", "tray_info_idx": ""}]
        scheduler = _scheduler_with({1: _need(RED)})
        assert await _hints(scheduler, {1: _status(vt=vt)}, [_job(1)], _holds(1)) == {}


def _dual(ams, fts=False, **fields):
    status = _status(ams, **fields)
    status.raw_data["ams_extruder_map"] = {"0": 0, "1": 1}
    status.fila_switch = FilaSwitchState(installed=fts)
    return status


class TestDualNozzle:
    AMS = [
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
    async def test_the_printer_has_a_part_per_nozzle_that_has_a_slot(self):
        scheduler = _scheduler_with({1: _need(RED)})
        hint = (await _hints(scheduler, {1: _dual(self.AMS)}, [_job(1)], _holds(1)))[1]
        assert [(n.nozzle, n.state) for n in hint.by_nozzle] == [("right", HINT_REPLACEABLE), ("left", HINT_FREE)]
        assert hint.state == HINT_FREE

    @pytest.mark.asyncio
    async def test_a_filament_track_switch_lifts_the_nozzle_filter(self):
        left = TodoFilament("PLA", "#FF69B4", "Pink", nozzle=1)
        right = TodoFilament("PLA", "#FF69B4", "Pink", nozzle=0)
        scheduler = _scheduler_with({1: _need(RED)})
        hint = (await _hints(scheduler, {1: _dual(self.AMS, fts=True)}, [_job(1)], _holds(1, filaments=(right, left))))[
            1
        ]
        assert hint.by_nozzle == ()
        assert {s.nozzle for s in hint.slots} == {None}
        assert [(s.ams_id, s.tray_id) for s in hint.slots] == [(1, 1)]

    @pytest.mark.asyncio
    async def test_a_single_nozzle_printer_names_no_nozzle(self):
        scheduler = _scheduler_with({1: _need(RED)})
        hint = (await _hints(scheduler, {1: _status(_loaded_ams(RED, BLUE))}, [_job(1)], _holds(1)))[1]
        assert [s.nozzle for s in hint.slots] == [None]


class TestModelJobs:
    @pytest.mark.asyncio
    async def test_a_model_job_that_fits_claims_trays(self, queue_db):
        ams = _loaded_ams(RED, BLUE)
        job = _job(2, printer_id=None, target_model="X1C")
        scheduler = _scheduler_with({1: _need(RED), 2: _need(BLUE)})
        async with queue_db.session_maker() as db:
            hints = await _hints(scheduler, {1: _status(ams)}, [_job(1), job], _holds(1), db=db)
        assert hints[1].state == HINT_ALL_NEEDED

    @pytest.mark.asyncio
    async def test_a_model_job_of_another_model_claims_nothing(self, queue_db):
        ams = _loaded_ams(RED, BLUE)
        job = _job(2, printer_id=None, target_model="P1S")
        scheduler = _scheduler_with({1: _need(RED), 2: _need(BLUE)})
        async with queue_db.session_maker() as db:
            hints = await _hints(scheduler, {1: _status(ams)}, [_job(1), job], _holds(1), db=db)
        assert [s.tray_id for s in hints[1].slots] == [1]

    @pytest.mark.asyncio
    async def test_a_model_job_whose_creator_may_not_use_the_printer_claims_nothing(self, queue_db):
        ams = _loaded_ams(RED, BLUE)
        job = _job(2, printer_id=None, target_model="X1C", created_by_id=7)
        scheduler = _scheduler_with({1: _need(RED), 2: _need(BLUE)})
        scheduler._creator_printer_scope = AsyncMock(return_value=PrinterScope(frozenset({2, 3})))
        async with queue_db.session_maker() as db:
            hints = await _hints(scheduler, {1: _status(ams)}, [_job(1), job], _holds(1), db=db)
        assert [s.tray_id for s in hints[1].slots] == [1]

    @pytest.mark.asyncio
    async def test_a_model_job_of_a_real_row_in_another_location_claims_nothing(self, queue_db):
        ams = _loaded_ams(RED, BLUE)
        job = _job(2, printer_id=None, target_model="X1C", target_location="Basement")
        scheduler = _scheduler_with({1: _need(RED), 2: _need(BLUE)})
        async with queue_db.session_maker() as db:
            hints = await _hints(scheduler, {1: _status(ams)}, [_job(1), job], _holds(1), db=db)
        assert [s.tray_id for s in hints[1].slots] == [1]


class TestInThePass:
    async def _pass(self, ctx, scheduler, status):
        launched = MagicMock()
        patches = [
            patch("backend.app.services.print_scheduler.async_session", ctx.session_maker),
            patch("backend.app.core.database.async_session", ctx.session_maker),
            patch("backend.app.services.print_scheduler.printer_manager.is_connected", MagicMock(return_value=True)),
            patch("backend.app.services.print_scheduler.printer_manager.get_status", MagicMock(return_value=status)),
            patch(
                "backend.app.services.print_scheduler.ha_sensor_manager.blocked_printers",
                AsyncMock(return_value={}),
            ),
            patch("backend.app.services.notification_service.notification_service.on_queue_job_waiting", AsyncMock()),
            patch("backend.app.services.print_scheduler.compute_deficit_for_queue_item", AsyncMock(return_value=[])),
            patch.object(scheduler, "_is_printer_idle", MagicMock(return_value=True)),
            patch.object(scheduler, "_check_auto_drying", AsyncMock()),
            patch.object(scheduler, "_launch_uploads", launched),
        ]
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            await scheduler.check_queue()
        return launched

    @pytest.mark.asyncio
    async def test_a_held_printer_gets_its_hint_and_the_job_is_held_as_before(self, queue_db):
        item_id = await _add_item(queue_db, printer_id=1, target_model=None)
        scheduler = _scheduler_with({item_id: _need(RED)})
        # PETG only, and an empty slot: the red PLA job has nothing to match.
        ams = [{"id": 0, "tray": [_tray(0, "PETG", BLUE), _tray(1, exists=False)]}]

        launched = await self._pass(queue_db, scheduler, _status(ams))

        launched.assert_not_called()
        (hold,) = scheduler.filament_holds_snapshot()[item_id]
        assert hold.printer_id == 1
        hint = scheduler.slot_hints_snapshot()[1]
        assert (hint.state, [(s.ams_id, s.tray_id) for s in hint.slots]) == (HINT_FREE, [(0, 1)])

    @pytest.mark.asyncio
    async def test_the_hint_goes_with_the_hold(self, queue_db):
        item_id = await _add_item(queue_db, printer_id=1, target_model=None)
        scheduler = _scheduler_with({item_id: _need(RED)})
        held = [{"id": 0, "tray": [_tray(0, "PETG", BLUE), _tray(1, exists=False)]}]
        await self._pass(queue_db, scheduler, _status(held))
        assert 1 in scheduler.slot_hints_snapshot()

        async with queue_db.session_maker() as db:
            await db.execute(delete(PrintQueueItem))
            await db.commit()
        await self._pass(queue_db, scheduler, _status(held))

        assert scheduler.slot_hints_snapshot() == {}
        assert scheduler.filament_holds_snapshot() == {}

    @pytest.mark.asyncio
    async def test_a_failing_hint_does_not_touch_the_pass(self, queue_db):
        item_id = await _add_item(queue_db, printer_id=1, target_model=None)
        scheduler = _scheduler_with({item_id: _need(RED)})
        scheduler._compute_slot_hints = AsyncMock(side_effect=RuntimeError("boom"))
        loaded = [{"id": 0, "tray": [_tray(0, "PETG", BLUE), _tray(1, exists=False)]}]

        await self._pass(queue_db, scheduler, _status(loaded))

        assert scheduler.slot_hints_snapshot() == {}
        assert item_id in scheduler.filament_holds_snapshot()


class TestUnitTypes:
    """Every kind of slot carries the gtid and the unit type the Printers page labels it by."""

    @staticmethod
    def _offered(hint):
        return [(s.ams_id, s.tray_id, s.is_ht, s.is_external, s.ams_type) for s in hint.slots]

    @pytest.mark.asyncio
    async def test_an_ams_ht_slot(self):
        ams = [{"id": 128, "tray": [_tray(0, exists=False)]}]
        scheduler = _scheduler_with({1: _need(RED)})
        hints = await _hints(scheduler, {1: _status(ams)}, [_job(1)], _holds(1))
        assert hints[1].state == HINT_FREE
        assert self._offered(hints[1]) == [(128, 0, True, False, 4)]

    @pytest.mark.asyncio
    async def test_an_ams_lite_slot(self):
        ams = [{"id": 0, "ams_type": 2, "tray": [_tray(0, "PLA", RED), _tray(1, exists=False)]}]
        scheduler = _scheduler_with({1: _need(RED)})
        hints = await _hints(scheduler, {1: _status(ams)}, [_job(1)], _holds(1))
        assert self._offered(hints[1]) == [(0, 1, False, False, 2)]

    @pytest.mark.asyncio
    async def test_an_ams_3h_slot_has_its_rack_gtid(self):
        ams = [{"id": 32, "ams_type": 6, "tray": [_tray(0, "PLA", RED), _tray(1, "PLA", BLUE)]}]
        # The job takes slot 0 (global tray 28); slot 1 is global tray 29.
        scheduler = _scheduler_with({1: _need(RED)})
        hints = await _hints(scheduler, {1: _status(ams)}, [_job(1)], _holds(1))
        assert hints[1].state == HINT_REPLACEABLE
        assert self._offered(hints[1]) == [(32, 1, False, False, 6)]

    @pytest.mark.asyncio
    async def test_the_external_holder(self):
        vt = [{"id": 254, "tray_type": "PETG", "tray_color": "00FF00FF", "tray_info_idx": ""}]
        scheduler = _scheduler_with({1: _need(RED)})
        hints = await _hints(scheduler, {1: _status(vt=vt)}, [_job(1)], _holds(1))
        assert self._offered(hints[1]) == [(-1, 0, False, True, None)]

    @pytest.mark.asyncio
    async def test_the_sub_brand_of_a_loaded_tray_goes_with_the_slot(self):
        ams = [{"id": 0, "tray": [_tray(0, "PLA", RED), _tray(1, "PLA", BLUE, tray_sub_brands="PLA Basic")]}]
        scheduler = _scheduler_with({1: _need(RED)})
        hints = await _hints(scheduler, {1: _status(ams)}, [_job(1)], _holds(1))
        assert [s.tray_sub_brands for s in hints[1].slots] == ["PLA Basic"]


class TestOtherCases:
    @pytest.mark.asyncio
    async def test_the_tray_in_use_and_the_one_of_the_mapping_can_differ(self):
        ams = _loaded_ams(RED, BLUE, WHITE, GREEN)
        # The print was started with tray 0 mapped; the extruder holds tray 2 now.
        running = _status(ams, state="RUNNING", print_ams_mapping=[0], tray_now=2)
        scheduler = _scheduler_with({1: _need(GREEN)})
        hints = await _hints(scheduler, {1: running}, [_job(1)], _holds(1))
        # 0 and 2 belong to the print, 3 to the waiting job.
        assert [s.tray_id for s in hints[1].slots] == [1]

    @pytest.mark.asyncio
    async def test_a_printer_no_longer_held_has_no_hint_while_other_items_wait(self):
        ams = _loaded_ams(RED, BLUE)
        scheduler = _scheduler_with({1: _need(RED), 2: _need(BLUE)})
        statuses = {1: _status(ams)}
        jobs = [_job(1), _job(2)]
        assert set(await _hints(scheduler, statuses, jobs, _holds(1))) == {1}
        assert await _hints(scheduler, statuses, jobs, {}) == {}
        assert scheduler._hint_memo == {}

    @pytest.mark.asyncio
    async def test_a_job_this_pass_marked_skipped_claims_nothing(self):
        ams = _loaded_ams(RED, BLUE)
        scheduler = _scheduler_with({1: _need(RED), 2: _need(BLUE)})
        hints = await _hints(scheduler, {1: _status(ams)}, [_job(1), _job(2, status="skipped")], _holds(1))
        assert [s.tray_id for s in hints[1].slots] == [1]

    @pytest.mark.asyncio
    async def test_staged_and_scheduled_rows_claim_their_trays(self, queue_db):
        from datetime import datetime, timedelta, timezone

        from sqlalchemy import select

        held = await _add_item(queue_db, printer_id=1, target_model=None)
        staged = await _add_item(queue_db, printer_id=1, target_model=None, manual_start=True)
        later = await _add_item(
            queue_db,
            printer_id=1,
            target_model=None,
            scheduled_time=datetime.now(timezone.utc) + timedelta(days=1),
        )
        ams = _loaded_ams(RED, BLUE, WHITE, GREEN)
        scheduler = _scheduler_with({held: _need(RED), staged: _need(BLUE), later: _need(WHITE)})
        async with queue_db.session_maker() as db:
            items = list((await db.execute(select(PrintQueueItem))).scalars().all())
            hints = await _hints(scheduler, {1: _status(ams)}, items, {held: _holds(1)[101]}, db=db)
        assert (hints[1].state, [s.tray_id for s in hints[1].slots]) == (HINT_REPLACEABLE, [3])

    @pytest.mark.asyncio
    async def test_a_failed_pass_keeps_the_hints_it_did_not_reach(self):
        from backend.app.services.queue_todo import SlotHint

        scheduler = PrintScheduler()
        scheduler._slot_hints = {1: SlotHint(1, HINT_FREE), 2: SlotHint(2, HINT_FREE)}

        async def half_a_pass():
            scheduler._pass_slot_hints[2] = SlotHint(2, HINT_ALL_NEEDED)
            raise RuntimeError("stopped early")

        scheduler._check_queue_pass = half_a_pass
        with pytest.raises(RuntimeError):
            await scheduler.check_queue()
        kept = scheduler.slot_hints_snapshot()
        assert (kept[1].state, kept[2].state) == (HINT_FREE, HINT_ALL_NEEDED)


class TestPassCost:
    """The hint step must not map, parse or query more than what changed (#3634)."""

    @staticmethod
    def _counted(requirements):
        scheduler = _scheduler_with(requirements)
        scheduler._planned_mapping = AsyncMock(wraps=scheduler._planned_mapping)
        return scheduler

    @pytest.mark.asyncio
    async def test_an_unchanged_second_pass_maps_nothing(self):
        scheduler = self._counted({1: _need(RED), 2: _need(BLUE)})
        statuses = {1: _status(_loaded_ams(RED, BLUE, WHITE))}
        jobs = [_job(1), _job(2)]
        first = await _hints(scheduler, statuses, jobs, _holds(1))
        mapped = scheduler._planned_mapping.await_count
        assert mapped == 2

        second = await _hints(scheduler, statuses, jobs, _holds(1))

        assert scheduler._planned_mapping.await_count == mapped
        assert second == first

    @pytest.mark.asyncio
    async def test_a_new_status_object_with_the_same_trays_is_still_unchanged(self):
        scheduler = self._counted({1: _need(RED)})
        await _hints(scheduler, {1: _status(_loaded_ams(RED, BLUE))}, [_job(1)], _holds(1))
        await _hints(scheduler, {1: _status(_loaded_ams(RED, BLUE))}, [_job(1)], _holds(1))
        assert scheduler._planned_mapping.await_count == 1

    @pytest.mark.asyncio
    async def test_a_tray_change_computes_again(self):
        scheduler = self._counted({1: _need(RED)})
        jobs = [_job(1)]
        await _hints(scheduler, {1: _status(_loaded_ams(RED, BLUE))}, jobs, _holds(1))
        hints = await _hints(scheduler, {1: _status(_loaded_ams(RED, GREEN))}, jobs, _holds(1))
        assert scheduler._planned_mapping.await_count == 2
        assert hints[1].slots[0].color == "#" + GREEN

    @pytest.mark.asyncio
    async def test_a_running_print_change_computes_again(self):
        scheduler = self._counted({1: _need(RED)})
        ams = _loaded_ams(RED, BLUE, WHITE)
        jobs = [_job(1)]
        await _hints(scheduler, {1: _status(ams)}, jobs, _holds(1))
        hints = await _hints(scheduler, {1: _status(ams, state="RUNNING", tray_now=2)}, jobs, _holds(1))
        assert scheduler._planned_mapping.await_count == 2
        assert [s.tray_id for s in hints[1].slots] == [1]

    @pytest.mark.asyncio
    async def test_a_job_change_computes_again(self):
        scheduler = self._counted({1: _need(RED), 2: _need(BLUE)})
        statuses = {1: _status(_loaded_ams(RED, BLUE, WHITE))}
        await _hints(scheduler, statuses, [_job(1)], _holds(1))
        # A job joins, and the first one gets a stored mapping.
        await _hints(scheduler, statuses, [_job(1), _job(2)], _holds(1))
        assert scheduler._planned_mapping.await_count == 3
        await _hints(scheduler, statuses, [_job(1, ams_mapping="[0]"), _job(2)], _holds(1))
        assert scheduler._planned_mapping.await_count == 5

    @pytest.mark.asyncio
    async def test_a_printer_that_is_not_held_any_more_is_forgotten(self):
        scheduler = self._counted({1: _need(RED)})
        statuses = {1: _status(_loaded_ams(RED, BLUE))}
        await _hints(scheduler, statuses, [_job(1)], _holds(1))
        await _hints(scheduler, statuses, [_job(1)], {})
        await _hints(scheduler, statuses, [_job(1)], _holds(1))
        assert scheduler._planned_mapping.await_count == 2

    @pytest.mark.asyncio
    async def test_jobs_that_map_the_same_way_are_mapped_once(self):
        scheduler = self._counted({1: _need(RED), 2: _need(RED), 3: _need(RED)})
        twins = [_job(1, archive_id=5), _job(2, archive_id=5), _job(3, archive_id=5)]
        hints = await _hints(scheduler, {1: _status(_loaded_ams(RED, BLUE))}, twins, _holds(1))
        assert scheduler._planned_mapping.await_count == 1
        assert [s.tray_id for s in hints[1].slots] == [1]

    @pytest.mark.asyncio
    async def test_jobs_that_differ_in_what_decides_the_mapping_are_mapped_each(self):
        scheduler = self._counted({i: _need(RED) for i in range(1, 6)})
        jobs = [
            _job(1, archive_id=5),
            _job(2, archive_id=5, plate_id=2),
            _job(3, archive_id=5, filament_overrides="[]"),
            _job(4, archive_id=5, ams_mapping="[0]"),
            _job(5, archive_id=5, created_by_id=3),
        ]
        await _hints(scheduler, {1: _status(_loaded_ams(RED, BLUE))}, jobs, _holds(1))
        assert scheduler._planned_mapping.await_count == 5

    @pytest.mark.asyncio
    async def test_unknown_twins_are_each_counted(self):
        scheduler = self._counted({1: None, 2: None})
        twins = [_job(1, archive_id=5), _job(2, archive_id=5)]
        hints = await _hints(scheduler, {1: _status(_loaded_ams(RED, BLUE))}, twins, _holds(1))
        assert hints[1].unknown_job_ids == (1, 2)

    @pytest.mark.asyncio
    async def test_the_setting_is_read_once_for_the_pass(self):
        scheduler = self._counted({1: _need(RED), 2: _need(BLUE)})
        statuses = {1: _status(_loaded_ams(RED, BLUE, WHITE)), 2: _status(_loaded_ams(RED, BLUE, WHITE))}
        await _hints(scheduler, statuses, [_job(1, printer_id=1), _job(2, printer_id=2)], _holds(1, 2))
        assert scheduler._get_bool_setting.await_count == 1
        assert {c.kwargs["prefer_lowest"] for c in scheduler._planned_mapping.await_args_list} == {False}

    @pytest.mark.asyncio
    async def test_the_hint_path_logs_nothing_at_info_but_dispatch_still_does(self, caplog):
        import logging

        scheduler = _scheduler_with({1: _need(RED)})
        scheduler._get_bool_setting = AsyncMock(return_value=True)
        scheduler._build_inventory_remain_overrides = AsyncMock(return_value={})
        # Backup off: prefer-lowest is skipped, with a line of its own.
        off = _status(_loaded_ams(RED, BLUE), ams_filament_backup=False)
        on = _status(_loaded_ams(RED, BLUE), ams_filament_backup=True)
        with caplog.at_level(logging.INFO, logger="backend.app.services.print_scheduler"):
            await _hints(scheduler, {1: off, 3: on}, [_job(1)], _holds(1, 3))
            quiet = [r for r in caplog.records if r.levelno == logging.INFO]
            assert quiet == []

            with patch("backend.app.services.print_scheduler.printer_manager.get_status", return_value=off):
                await scheduler._compute_ams_mapping_for_printer(AsyncMock(), 1, _job(1))
            with patch("backend.app.services.print_scheduler.printer_manager.get_status", return_value=on):
                await scheduler._compute_ams_mapping_for_printer(AsyncMock(), 3, _job(1))
        loud = " ".join(r.getMessage() for r in caplog.records if r.levelno == logging.INFO)
        assert "[prefer-lowest] skipped" in loud
        assert "[prefer-lowest] req slot" in loud


class TestFailures:
    @staticmethod
    def _warnings(caplog):
        import logging

        return [r for r in caplog.records if r.levelno == logging.WARNING and "no slot hint" in r.getMessage()]

    @pytest.mark.asyncio
    async def test_a_failing_printer_is_warned_about_once_until_it_works_again(self, caplog):
        scheduler = _scheduler_with({1: _need(RED)})
        statuses = {1: _status(_loaded_ams(RED, BLUE))}
        real = scheduler._slot_hint_for_printer
        scheduler._slot_hint_for_printer = AsyncMock(side_effect=RuntimeError("boom"))
        for _ in range(3):
            assert await _hints(scheduler, statuses, [_job(1)], _holds(1)) == {}
        assert len(self._warnings(caplog)) == 1

        scheduler._slot_hint_for_printer = real
        assert 1 in await _hints(scheduler, statuses, [_job(1)], _holds(1))
        scheduler._slot_hint_for_printer = AsyncMock(side_effect=RuntimeError("boom"))
        await _hints(scheduler, {1: _status(_loaded_ams(RED, GREEN))}, [_job(1)], _holds(1))
        assert len(self._warnings(caplog)) == 2

    @pytest.mark.asyncio
    async def test_a_failing_printer_does_not_hide_the_others(self):
        scheduler = _scheduler_with({1: _need(RED)})
        statuses = {1: _status(_loaded_ams(RED, BLUE)), 2: _status(_loaded_ams(RED, BLUE))}
        real = scheduler._slot_hint_for_printer

        async def pick(db, printer_id, *args):
            if printer_id == 1:
                raise RuntimeError("boom")
            return await real(db, printer_id, *args)

        scheduler._slot_hint_for_printer = pick
        hints = await _hints(scheduler, statuses, [_job(1, printer_id=1), _job(2, printer_id=2)], _holds(1, 2))
        assert set(hints) == {2}

    @pytest.mark.asyncio
    async def test_a_failed_hint_step_is_rolled_back_alone_and_the_pass_goes_on(self, queue_db):
        from sqlalchemy import event, text
        from sqlalchemy.orm import Session

        item_id = await _add_item(queue_db, printer_id=1, target_model=None)
        scheduler = _scheduler_with({item_id: _need(RED)})

        async def bad_query(db, items, holds):
            await db.execute(text("SELECT * FROM table_that_does_not_exist"))

        scheduler._compute_slot_hints = bad_query
        rolled_back = []
        listener = lambda session, previous: rolled_back.append(previous.nested)  # noqa: E731
        event.listen(Session, "after_soft_rollback", listener)
        try:
            loaded = [{"id": 0, "tray": [_tray(0, "PETG", BLUE), _tray(1, exists=False)]}]
            await TestInThePass()._pass(queue_db, scheduler, _status(loaded))
        finally:
            event.remove(Session, "after_soft_rollback", listener)

        # The savepoint went back; the session's own transaction was not rolled back.
        assert True in rolled_back
        assert item_id in scheduler.filament_holds_snapshot()
        assert scheduler.slot_hints_snapshot() == {}


class TestStaleMemo:
    @staticmethod
    def _counted(requirements):
        scheduler = _scheduler_with(requirements)
        scheduler._planned_mapping = AsyncMock(wraps=scheduler._planned_mapping)
        return scheduler

    @pytest.mark.asyncio
    async def test_a_hint_computed_with_a_failing_job_is_not_kept(self):
        scheduler = self._counted({1: _need(RED), 2: _need(BLUE)})
        scheduler._planned_mapping = AsyncMock(side_effect=[[0], RuntimeError("bad"), [0], [1]])
        statuses = {1: _status(_loaded_ams(RED, BLUE, WHITE))}
        jobs = [_job(1), _job(2)]
        assert 1 in await _hints(scheduler, statuses, jobs, _holds(1))
        assert scheduler._hint_memo == {}
        await _hints(scheduler, statuses, jobs, _holds(1))
        assert scheduler._planned_mapping.await_count == 4

    @pytest.mark.asyncio
    async def test_a_hint_with_an_unknown_job_is_not_kept(self):
        scheduler = self._counted({1: None})
        await _hints(scheduler, {1: _status(_loaded_ams(RED, BLUE))}, [_job(1)], _holds(1))
        assert scheduler._hint_memo == {}

    @pytest.mark.asyncio
    async def test_a_rolled_back_hint_step_keeps_no_memo(self, queue_db):
        item_id = await _add_item(queue_db, printer_id=1, target_model=None)
        scheduler = _scheduler_with({item_id: _need(RED)})
        real = scheduler._compute_slot_hints

        async def then_fail(db, items, holds):
            await real(db, items, holds)
            raise RuntimeError("after the work")

        scheduler._compute_slot_hints = then_fail
        loaded = [{"id": 0, "tray": [_tray(0, "PETG", BLUE), _tray(1, exists=False)]}]
        await TestInThePass()._pass(queue_db, scheduler, _status(loaded))
        assert scheduler._hint_memo == {}

    @pytest.mark.asyncio
    async def test_a_replaced_archive_file_computes_again(self):
        scheduler = self._counted({1: _need(RED)})
        statuses = {1: _status(_loaded_ams(RED, BLUE))}
        jobs = [_job(1)]

        def db_with(content_hash):
            db = AsyncMock()
            db.execute = AsyncMock(return_value=[(1, content_hash, "archives/a.3mf")])
            return db

        await _hints(scheduler, statuses, jobs, _holds(1), db=db_with("aaa"))
        await _hints(scheduler, statuses, jobs, _holds(1), db=db_with("aaa"))
        assert scheduler._planned_mapping.await_count == 1
        await _hints(scheduler, statuses, jobs, _holds(1), db=db_with("bbb"))
        assert scheduler._planned_mapping.await_count == 2

    @pytest.mark.asyncio
    async def test_a_trashed_library_file_computes_again(self, queue_db):
        from datetime import datetime, timezone

        from sqlalchemy import select, update

        from backend.app.models.library import LibraryFile

        item_id = await _add_item(queue_db, printer_id=1, target_model=None)
        scheduler = self._counted({item_id: _need(RED)})
        statuses = {1: _status(_loaded_ams(RED, BLUE))}
        holds = {item_id: _holds(1)[101]}

        async def run():
            async with queue_db.session_maker() as db:
                items = list((await db.execute(select(PrintQueueItem))).scalars().all())
                return await _hints(scheduler, statuses, items, holds, db=db)

        await run()
        await run()
        assert scheduler._planned_mapping.await_count == 1
        async with queue_db.session_maker() as db:
            await db.execute(update(LibraryFile).values(deleted_at=datetime.now(timezone.utc).replace(tzinfo=None)))
            await db.commit()
        await run()
        assert scheduler._planned_mapping.await_count == 2

    @pytest.mark.asyncio
    async def test_an_external_holder_reported_empty_versus_absent_computes_again(self):
        scheduler = self._counted({1: _need(RED)})
        ams = _loaded_ams(RED, BLUE)
        empty_vt = [{"id": 254, "tray_type": "", "tray_color": "", "tray_info_idx": ""}]
        await _hints(scheduler, {1: _status(ams)}, [_job(1)], _holds(1))
        await _hints(scheduler, {1: _status(ams, vt=empty_vt)}, [_job(1)], _holds(1))
        assert scheduler._planned_mapping.await_count == 2

    @pytest.mark.asyncio
    async def test_a_pass_with_no_held_printer_forgets_memo_and_warnings(self, queue_db):
        # A job the printer can take: no hold.
        item_id = await _add_item(queue_db, printer_id=1, target_model=None)
        scheduler = _scheduler_with({item_id: _need(RED)})
        scheduler._hint_memo = {1: (("x",), None)}
        scheduler._hint_warned = {1}
        await TestInThePass()._pass(queue_db, scheduler, _status(_loaded_ams(RED)))
        assert (scheduler._hint_memo, scheduler._hint_warned) == ({}, set())
