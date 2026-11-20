"""What a printer's next jobs need and where it can go without touching the running print (#3640)."""

import json
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import delete

from backend.app.models.print_queue import PrintQueueItem
from backend.app.services.bambu_mqtt import ExtruderSlot
from backend.app.services.queue_todo import (
    HINT_ALL_NEEDED,
    HINT_FREE,
    HINT_REPLACEABLE,
    FilamentHold,
    HintSlot,
    ShortTray,
    SlotHint,
    TodoFilament,
    _hint_dict,
    settled_hint,
)
from backend.tests.unit.test_scheduler_model_filament_short_3137 import (
    _add_item,
    queue_db,  # noqa: F401 - fixture
)
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

CYAN = "00FFFF"


def _req(*specs):
    """Requirements of (type, colour) per slot: the matcher goes by type, so a job misses a filament of a type nothing loaded has."""
    return [{"slot_id": i + 1, "type": t, "color": "#" + c, "tray_info_idx": ""} for i, (t, c) in enumerate(specs)]


# Loaded: red, blue, white, green PLA (trays 0-3). A job that needs red PLA and pink PETG misses the PETG.
RED_PINK = _req(("PLA", RED), ("PETG", "FF69B4"))
RED_CYAN = _req(("PLA", RED), ("ASA", CYAN))


async def _prepare(
    scheduler,
    statuses,
    items,
    holds=None,
    db=None,
    running_rows=None,
    connected=lambda pid: True,
    slot_hints=None,
    shared=None,
):
    """Run the prepare step the way the pass does, and keep its memo as the pass does."""
    scheduler._running_mapping_trays = AsyncMock(return_value=running_rows or {})
    with (
        patch(
            "backend.app.services.print_scheduler.printer_manager.get_status",
            MagicMock(side_effect=lambda pid: statuses.get(pid)),
        ),
        patch(
            "backend.app.services.print_scheduler.printer_manager.get_all_statuses", MagicMock(return_value=statuses)
        ),
        patch("backend.app.services.print_scheduler.printer_manager.is_connected", MagicMock(side_effect=connected)),
    ):
        entries, memo = await scheduler._compute_prepare(db or AsyncMock(), items, holds or {}, shared, slot_hints)
    scheduler._hint_memo = memo
    return entries


def _printing(ams, mapping=(0,), **fields):
    return _status(
        ams, state="RUNNING", print_ams_mapping=list(mapping), tray_now=mapping[0] if mapping else 255, **fields
    )


def _next_job(item_id, **fields):
    return _job(item_id, scheduled_time=None, manual_start=False, **fields)


def _slots(entry):
    return [(s.ams_id, s.tray_id) for s in entry.hint.slots]


class TestPrinting:
    @pytest.mark.asyncio
    async def test_the_next_job_is_named_with_what_it_misses_and_where_it_can_go(self):
        ams = _loaded_ams(RED, BLUE, WHITE, GREEN)
        scheduler = _scheduler_with({2: RED_PINK})
        entries = await _prepare(scheduler, {1: _printing(ams)}, [_next_job(2)])
        (entry,) = entries[1]
        assert (entry.item_id, entry.position) == (2, 1)
        assert [(f.type, f.color) for f in entry.filaments] == [("PETG", "#FF69B4")]
        # Tray 0 is the print's, and the next job prints red on it as well.
        assert entry.hint.state == HINT_REPLACEABLE
        assert _slots(entry) == [(0, 1), (0, 2), (0, 3)]

    @pytest.mark.asyncio
    async def test_a_job_that_misses_nothing_gets_no_line_but_keeps_its_trays(self):
        ams = _loaded_ams(RED, BLUE, WHITE, GREEN)
        scheduler = _scheduler_with({2: _need(BLUE), 3: RED_PINK})
        entries = await _prepare(scheduler, {1: _printing(ams)}, [_next_job(2), _next_job(3)])
        (entry,) = entries[1]
        assert (entry.item_id, entry.position) == (3, 1)
        # Blue is the nearer job's.
        assert _slots(entry) == [(0, 2), (0, 3)]

    @pytest.mark.asyncio
    async def test_only_the_first_two_jobs_that_miss_something_get_a_line(self):
        ams = _loaded_ams(RED, BLUE, WHITE, GREEN)
        scheduler = _scheduler_with({2: RED_PINK, 3: RED_CYAN, 4: RED_PINK})
        entries = await _prepare(scheduler, {1: _printing(ams)}, [_next_job(2), _next_job(3), _next_job(4)])
        assert [(e.item_id, e.position) for e in entries[1]] == [(2, 1), (3, 2)]

    @pytest.mark.asyncio
    async def test_the_second_job_is_offered_what_the_first_would_not_take(self):
        ams = _loaded_ams(RED, BLUE, WHITE, GREEN)
        scheduler = _scheduler_with({2: RED_PINK, 3: RED_CYAN})
        first, second = (await _prepare(scheduler, {1: _printing(ams)}, [_next_job(2), _next_job(3)]))[1]
        assert _slots(first) == [(0, 1), (0, 2), (0, 3)]
        assert _slots(second) == [(0, 2), (0, 3)]

    @pytest.mark.asyncio
    async def test_the_first_job_takes_as_many_slots_as_it_misses_filaments(self):
        ams = _loaded_ams(RED, BLUE, WHITE, GREEN)
        scheduler = _scheduler_with({2: _req(("PLA", RED), ("PETG", "FF69B4"), ("ASA", "FFA500")), 3: RED_CYAN})
        first, second = (await _prepare(scheduler, {1: _printing(ams)}, [_next_job(2), _next_job(3)]))[1]
        assert len(first.filaments) == 2
        assert _slots(second) == [(0, 3)]

    @pytest.mark.asyncio
    async def test_the_second_job_may_be_left_with_nothing(self):
        ams = _loaded_ams(RED, BLUE)
        scheduler = _scheduler_with({2: RED_PINK, 3: RED_CYAN})
        first, second = (await _prepare(scheduler, {1: _printing(ams)}, [_next_job(2), _next_job(3)]))[1]
        assert _slots(first) == [(0, 1)]
        assert (second.hint.state, second.hint.slots) == (HINT_ALL_NEEDED, ())

    @pytest.mark.asyncio
    async def test_a_free_slot_is_offered_before_loaded_ones(self):
        ams = [{"id": 0, "tray": [_tray(0, "PLA", RED), _tray(1, "PLA", BLUE), _tray(2, exists=False)]}]
        scheduler = _scheduler_with({2: RED_PINK})
        (entry,) = (await _prepare(scheduler, {1: _printing(ams)}, [_next_job(2)]))[1]
        assert (entry.hint.state, _slots(entry)) == (HINT_FREE, [(0, 2)])

    @pytest.mark.asyncio
    async def test_the_tray_the_extruder_holds_is_never_offered(self):
        ams = _loaded_ams(RED, BLUE, WHITE)
        status = _printing(ams, extruder_slots={0: ExtruderSlot(ams_id=0, slot_id=2, has_filament=True)})
        scheduler = _scheduler_with({2: RED_PINK})
        (entry,) = (await _prepare(scheduler, {1: status}, [_next_job(2)]))[1]
        assert _slots(entry) == [(0, 1)]

    @pytest.mark.asyncio
    async def test_a_paused_print_keeps_the_slots_it_expects_and_has_left(self):
        ams = _loaded_ams(RED, BLUE, WHITE, GREEN)
        status = _status(ams, state="PAUSE", print_ams_mapping=[0], tray_now=0, tray_tar=2, tray_pre=3)
        scheduler = _scheduler_with({2: RED_PINK})
        (entry,) = (await _prepare(scheduler, {1: status}, [_next_job(2)]))[1]
        assert _slots(entry) == [(0, 1)]

    @pytest.mark.asyncio
    async def test_a_paused_print_s_runout_slots_are_not_offered_by_a_line_nor_a_hint(self):
        # Tray 2 ran out and the printer expects tray 3 (#3648): the Prepare line and the Load hint both skip them.
        ams = _loaded_ams(RED, BLUE, WHITE, GREEN)
        status = _status(ams, state="PAUSE", print_ams_mapping=[0], tray_now=0, tray_tar=3, tray_pre=2)
        scheduler = _scheduler_with({1: _need(RED), 2: RED_PINK})
        hints = await _hints(scheduler, {1: status}, [_job(1)], _holds(1))
        assert [s.tray_id for s in hints[1].slots] == [1]
        (entry,) = (await _prepare(scheduler, {1: status}, [_next_job(2)]))[1]
        assert _slots(entry) == [(0, 1)]

    @pytest.mark.asyncio
    async def test_a_printer_that_reported_no_trays_has_no_line(self):
        scheduler = _scheduler_with({2: RED_PINK})
        assert await _prepare(scheduler, {1: _printing([])}, [_next_job(2)]) == {}

    @pytest.mark.asyncio
    async def test_a_printer_that_is_not_printing_and_holds_nothing_has_no_line(self):
        ams = _loaded_ams(RED, BLUE)
        scheduler = _scheduler_with({2: RED_PINK})
        assert await _prepare(scheduler, {1: _status(ams)}, [_next_job(2)]) == {}

    @pytest.mark.asyncio
    async def test_a_job_the_printer_cannot_be_given_alone_has_no_line(self):
        ams = _loaded_ams(RED, BLUE)
        other = _next_job(2, printer_id=2)
        model = _next_job(3, printer_id=None, target_model="X1C")
        scheduler = _scheduler_with({2: RED_PINK, 3: RED_PINK})
        scheduler._model_job_printer_ids = AsyncMock(return_value={1, 2})
        scheduler._creator_printer_scope = AsyncMock(return_value=MagicMock())
        assert await _prepare(scheduler, {1: _printing(ams)}, [other, model]) == {}


class TestRunningMappingUnknown:
    @pytest.mark.asyncio
    async def test_no_mapping_no_line(self):
        ams = _loaded_ams(RED, BLUE, WHITE)
        scheduler = _scheduler_with({2: RED_PINK})
        assert await _prepare(scheduler, {1: _printing(ams, mapping=())}, [_next_job(2)]) == {}

    @pytest.mark.asyncio
    async def test_a_mapping_of_nothing_but_unresolved_slots_is_no_mapping(self):
        ams = _loaded_ams(RED, BLUE, WHITE)
        scheduler = _scheduler_with({2: RED_PINK})
        assert await _prepare(scheduler, {1: _printing(ams, mapping=(-1, -1))}, [_next_job(2)]) == {}

    @pytest.mark.asyncio
    async def test_the_queue_row_of_the_running_print_gives_the_mapping(self):
        ams = _loaded_ams(RED, BLUE, WHITE)
        scheduler = _scheduler_with({2: RED_PINK})
        entries = await _prepare(scheduler, {1: _printing(ams, mapping=())}, [_next_job(2)], running_rows={1: {2}})
        # Tray 2 is the running print's; tray 0 is the next job's red.
        assert _slots(entries[1][0]) == [(0, 1)]

    @pytest.mark.asyncio
    async def test_the_queue_row_is_read_from_the_database(self, queue_db):
        await _add_item(queue_db, printer_id=1, target_model=None, status="printing", ams_mapping=json.dumps([2]))
        await _add_item(queue_db, printer_id=2, target_model=None, status="printing", ams_mapping="not json")
        scheduler = _scheduler_with({})
        async with queue_db.session_maker() as db:
            assert await scheduler._running_mapping_trays(db, {1, 2, 3}) == {1: {2}, 2: set()}
            assert await scheduler._running_mapping_trays(db, set()) == {}


class TestFilamentBackup:
    # Trays 0 and 1 hold the same red PLA: tray 1 would take over when tray 0 runs out.
    AMS = [
        {"id": 0, "tray": [_tray(0, "PLA", RED), _tray(1, "PLA", RED), _tray(2, "PLA", BLUE), _tray(3, "PLA", WHITE)]}
    ]

    async def _offered(self, backup):
        scheduler = _scheduler_with({2: _req(("PLA", WHITE), ("PETG", "FF69B4"))})
        status = _printing(self.AMS, ams_filament_backup=backup)
        (entry,) = (await _prepare(scheduler, {1: status}, [_next_job(2)]))[1]
        return [tray for _ams, tray in _slots(entry)]

    @pytest.mark.asyncio
    async def test_a_backup_peer_of_a_running_tray_is_never_offered(self):
        assert await self._offered(True) == [2]

    @pytest.mark.asyncio
    async def test_without_the_backup_it_can_be_replaced(self):
        assert await self._offered(False) == [1, 2]

    @pytest.mark.asyncio
    async def test_an_unreported_backup_setting_is_read_as_on(self):
        assert await self._offered(None) == [2]

    @pytest.mark.asyncio
    async def test_a_slot_of_another_colour_is_no_peer(self):
        ams = [{"id": 0, "tray": [_tray(0, "PLA", RED), _tray(1, "PLA", "FF0001"), _tray(2, "PLA", BLUE)]}]
        scheduler = _scheduler_with({2: RED_PINK})
        (entry,) = (await _prepare(scheduler, {1: _printing(ams, ams_filament_backup=True)}, [_next_job(2)]))[1]
        assert [tray for _a, tray in _slots(entry)] == [1, 2]

    @pytest.mark.asyncio
    async def test_the_preset_decides_when_the_tray_reports_one(self):
        ams = [
            {
                "id": 0,
                "tray": [
                    _tray(0, "PLA", RED, tray_info_idx="GFA00"),
                    _tray(1, "PLA", RED, tray_info_idx="GFA01"),
                    _tray(2, "PLA", RED, tray_info_idx="GFA00"),
                ],
            }
        ]
        scheduler = _scheduler_with({2: RED_PINK})
        status = _printing(ams, ams_filament_backup=True)
        (entry,) = (await _prepare(scheduler, {1: status}, [_next_job(2)]))[1]
        assert [tray for _a, tray in _slots(entry)] == [1]

    @pytest.mark.asyncio
    async def test_a_peer_on_the_other_nozzle_is_no_peer(self):
        ams = [
            {"id": 0, "tray": [_tray(0, "PLA", RED), _tray(1, "PLA", BLUE)]},
            {"id": 1, "tray": [_tray(0, "PLA", RED), _tray(1, "PLA", WHITE)]},
        ]
        scheduler = _scheduler_with({2: RED_PINK})
        status = _dual(ams, state="RUNNING", print_ams_mapping=[0], tray_now=0, ams_filament_backup=True)
        (entry,) = (await _prepare(scheduler, {1: status}, [_next_job(2)]))[1]
        assert (1, 0) in _slots(entry)
        assert (0, 1) in _slots(entry)

    @pytest.mark.asyncio
    async def test_a_filament_track_switch_lets_a_peer_on_any_nozzle_take_over(self):
        ams = [
            {"id": 0, "tray": [_tray(0, "PLA", RED), _tray(1, "PLA", BLUE)]},
            {"id": 1, "tray": [_tray(0, "PLA", RED), _tray(1, "PLA", WHITE)]},
        ]
        scheduler = _scheduler_with({2: RED_PINK})
        status = _dual(ams, fts=True, state="RUNNING", print_ams_mapping=[0], tray_now=0, ams_filament_backup=True)
        (entry,) = (await _prepare(scheduler, {1: status}, [_next_job(2)]))[1]
        assert (1, 0) not in _slots(entry)


class TestDualNozzle:
    AMS = [
        {"id": 0, "tray": [_tray(0, "PLA", RED), _tray(1, "PLA", BLUE), _tray(2, "PLA", WHITE)]},
        {"id": 1, "tray": [_tray(0, "PLA", GREEN), _tray(1, exists=False), _tray(2, "PLA", "123456")]},
    ]

    @pytest.mark.asyncio
    async def test_the_running_print_s_trays_are_kept_on_both_nozzles(self):
        scheduler = _scheduler_with({2: RED_PINK})
        status = _dual(self.AMS, state="RUNNING", print_ams_mapping=[0, 4], tray_now=0)
        (entry,) = (await _prepare(scheduler, {1: status}, [_next_job(2)]))[1]
        assert [(p.nozzle, p.state) for p in entry.hint.by_nozzle] == [("right", HINT_REPLACEABLE), ("left", HINT_FREE)]
        right = entry.hint.by_nozzle[0]
        assert [(s.ams_id, s.tray_id) for s in right.slots] == [(0, 1), (0, 2)]

    @pytest.mark.asyncio
    async def test_a_filament_that_names_a_nozzle_takes_from_that_nozzle_for_the_second_job(self):
        scheduler = _scheduler_with({2: _need(RED), 3: _need(RED)})
        scheduler._unmatched_requirements = AsyncMock(
            side_effect=lambda db, item, pid, mapping: [
                {"type": "PETG" if item.id == 2 else "ASA", "color": "#FF69B4", "nozzle_id": 1}
            ]
        )
        status = _dual(self.AMS, state="RUNNING", print_ams_mapping=[0], tray_now=0)
        first, second = (await _prepare(scheduler, {1: status}, [_next_job(2), _next_job(3)]))[1]
        assert [f.nozzle for f in first.filaments] == [1]
        # Job one takes the free slot of the left nozzle; job two has the left AMS's loaded ones.
        left_of_second = [p for p in second.hint.by_nozzle if p.nozzle == "left"][0]
        assert (left_of_second.state, [(s.ams_id, s.tray_id) for s in left_of_second.slots]) == (
            HINT_REPLACEABLE,
            [(1, 0), (1, 2)],
        )


class TestUnitKinds:
    @pytest.mark.asyncio
    async def test_a_free_ams_ht_slot_is_offered(self):
        ams = [{"id": 0, "tray": [_tray(0, "PLA", RED)]}, {"id": 128, "tray": [_tray(0, exists=False)]}]
        scheduler = _scheduler_with({2: RED_PINK})
        (entry,) = (await _prepare(scheduler, {1: _printing(ams)}, [_next_job(2)]))[1]
        assert (entry.hint.state, [(s.ams_id, s.is_ht) for s in entry.hint.slots]) == (HINT_FREE, [(128, True)])

    @pytest.mark.asyncio
    async def test_an_ams_ht_slot_of_the_print_is_kept(self):
        ams = [{"id": 128, "tray": [_tray(0, "PLA", RED)]}, {"id": 129, "tray": [_tray(0, "PLA", BLUE)]}]
        scheduler = _scheduler_with({2: _req(("PLA", BLUE), ("PETG", "FF69B4"))})
        status = _printing(ams, mapping=(128,), ams_filament_backup=False)
        (entry,) = (await _prepare(scheduler, {1: status}, [_next_job(2)]))[1]
        assert (entry.hint.state, entry.hint.slots) == (HINT_ALL_NEEDED, ())

    @pytest.mark.asyncio
    async def test_an_external_spool_the_print_uses_is_not_offered(self):
        vt = [{"id": 254, "tray_type": "PETG", "tray_color": "00FF00FF", "tray_info_idx": ""}]
        scheduler = _scheduler_with({2: _need(RED)})
        status = _status(vt=vt, state="RUNNING", print_ams_mapping=[254], tray_now=254)
        entries = await _prepare(scheduler, {1: status}, [_next_job(2)])
        (entry,) = entries[1]
        assert (entry.hint.state, entry.hint.slots) == (HINT_ALL_NEEDED, ())

    @pytest.mark.asyncio
    async def test_an_external_spool_the_print_does_not_use_follows_the_rule_of_the_hint(self):
        vt = [{"id": 254, "tray_type": "ABS", "tray_color": "00FF00FF", "tray_info_idx": ""}]
        ams = [{"id": 0, "tray": [_tray(0, "PLA", RED)]}]
        scheduler = _scheduler_with({2: RED_PINK})
        status = _status(ams, vt=vt, state="RUNNING", print_ams_mapping=[0], tray_now=0)
        (entry,) = (await _prepare(scheduler, {1: status}, [_next_job(2)]))[1]
        # An AMS slot exists on the printer, so the holder is not offered.
        assert (entry.hint.state, entry.hint.slots) == (HINT_ALL_NEEDED, ())


class TestHeldJobs:
    @pytest.mark.asyncio
    async def test_a_job_that_holds_gets_no_line_but_its_trays_stay_reserved(self):
        ams = _loaded_ams(RED, BLUE, WHITE)
        held = _next_job(2)
        scheduler = _scheduler_with({2: _req(("PLA", BLUE), ("PETG", "FF69B4")), 3: RED_PINK})
        holds = {2: [FilamentHold(2, 1, None, (PINK,))]}
        entries = await _prepare(scheduler, {1: _status(ams)}, [held, _next_job(3)], holds)
        (entry,) = entries[1]
        assert entry.item_id == 3
        # The idle printer's held job keeps blue; the next job needs red.
        assert _slots(entry) == [(0, 2)]

    @pytest.mark.asyncio
    async def test_an_idle_printer_with_nothing_after_the_held_job_has_no_line(self):
        ams = _loaded_ams(RED, BLUE)
        scheduler = _scheduler_with({2: RED_PINK})
        holds = {2: [FilamentHold(2, 1, None, (PINK,))]}
        assert await _prepare(scheduler, {1: _status(ams)}, [_next_job(2)], holds) == {}

    @pytest.mark.asyncio
    async def test_unknown_filaments_of_a_nearer_job_are_counted(self):
        ams = _loaded_ams(RED, BLUE, WHITE)
        scheduler = _scheduler_with({2: None, 3: RED_PINK})
        (entry,) = (await _prepare(scheduler, {1: _printing(ams)}, [_next_job(2), _next_job(3)]))[1]
        assert entry.hint.unknown_job_ids == (2,)


class TestHeldJobOffers:
    """The slots a held job's Load entry offers are not suggested again by a Prepare line (#3640)."""

    AMS = _loaded_ams(RED, BLUE, WHITE, GREEN)

    @pytest.mark.asyncio
    async def test_the_next_job_is_not_offered_the_slot_the_held_job_would_take(self):
        # The held job misses pink PETG, the next job misses cyan ASA.
        scheduler = _scheduler_with({2: RED_PINK, 3: RED_CYAN})
        holds = {2: [FilamentHold(2, 1, None, (PINK,))]}
        (entry,) = (await _prepare(scheduler, {1: _status(self.AMS)}, [_next_job(2), _next_job(3)], holds))[1]
        assert entry.item_id == 3
        # Red is the held job's, blue is what its Load entry offers.
        assert _slots(entry) == [(0, 2), (0, 3)]

    @pytest.mark.asyncio
    async def test_the_hint_the_load_entry_shows_is_the_one_that_is_kept_out(self):
        from backend.app.services.queue_todo import HintSlot, SlotHint

        scheduler = _scheduler_with({2: RED_PINK, 3: RED_CYAN})
        holds = {2: [FilamentHold(2, 1, None, (PINK,))]}
        offered = SlotHint(1, HINT_REPLACEABLE, (HintSlot(0, 2, False, False, 0, None, "PLA", "#FFFFFF"),))
        entries = await _prepare(
            scheduler, {1: _status(self.AMS)}, [_next_job(2), _next_job(3)], holds, slot_hints={1: offered}
        )
        assert _slots(entries[1][0]) == [(0, 1), (0, 3)]

    @pytest.mark.asyncio
    async def test_a_held_job_that_misses_two_filaments_keeps_two_slots(self):
        scheduler = _scheduler_with({2: RED_PINK, 3: RED_CYAN})
        holds = {2: [FilamentHold(2, 1, None, (PINK, TodoFilament("ASA", "#FFA500")))]}
        (entry,) = (await _prepare(scheduler, {1: _status(self.AMS)}, [_next_job(2), _next_job(3)], holds))[1]
        assert _slots(entry) == [(0, 3)]

    @pytest.mark.asyncio
    async def test_a_changed_hold_computes_again(self):
        scheduler = _scheduler_with({2: RED_PINK, 3: RED_CYAN})
        jobs = [_next_job(2), _next_job(3)]
        statuses = {1: _status(self.AMS)}
        await _prepare(scheduler, statuses, jobs, {2: [FilamentHold(2, 1, None, (PINK,))]})
        scheduler._planned_mapping = AsyncMock(wraps=scheduler._planned_mapping)
        await _prepare(
            scheduler, statuses, jobs, {2: [FilamentHold(2, 1, None, (PINK, TodoFilament("ASA", "#FFA500")))]}
        )
        scheduler._planned_mapping.assert_called()


class TestOverflow:
    @pytest.mark.asyncio
    async def test_filaments_beyond_the_free_slots_take_loaded_slots_from_the_next_job(self):
        # One free slot (3) for a job that misses two filaments: the second takes the first replaceable one.
        ams = [
            {
                "id": 0,
                "tray": [_tray(0, "PLA", RED), _tray(1, "PLA", BLUE), _tray(2, "PLA", WHITE), _tray(3, exists=False)],
            }
        ]
        scheduler = _scheduler_with({2: _req(("PLA", RED), ("PETG", "FF69B4"), ("ASA", "FFA500")), 3: RED_CYAN})
        first, second = (await _prepare(scheduler, {1: _printing(ams)}, [_next_job(2), _next_job(3)]))[1]
        assert (first.hint.state, _slots(first)) == (HINT_FREE, [(0, 3)])
        assert (second.hint.state, _slots(second)) == (HINT_REPLACEABLE, [(0, 2)])


class TestListedOnce:
    @pytest.mark.asyncio
    async def test_a_filament_of_a_nearer_job_is_not_listed_again(self):
        scheduler = _scheduler_with({2: RED_PINK, 3: _req(("PLA", RED), ("PETG", "FF69B4"), ("ASA", CYAN))})
        first, second = (
            await _prepare(scheduler, {1: _printing(_loaded_ams(RED, BLUE, WHITE))}, [_next_job(2), _next_job(3)])
        )[1]
        assert [(f.type, f.color) for f in first.filaments] == [("PETG", "#FF69B4")]
        assert [(f.type, f.color) for f in second.filaments] == [("ASA", "#00FFFF")]
        assert (second.item_id, second.position) == (3, 2)

    @pytest.mark.asyncio
    async def test_a_job_with_nothing_new_has_no_line_and_the_next_one_takes_its_place(self):
        scheduler = _scheduler_with({2: RED_PINK, 3: RED_PINK, 4: RED_CYAN})
        entries = (
            await _prepare(
                scheduler,
                {1: _printing(_loaded_ams(RED, BLUE, WHITE))},
                [_next_job(2), _next_job(3), _next_job(4)],
            )
        )[1]
        assert [(e.item_id, e.position) for e in entries] == [(2, 1), (4, 2)]

    @pytest.mark.asyncio
    async def test_the_same_filament_on_another_nozzle_is_listed(self):
        left = [{"slot_id": 1, "type": "PETG", "color": "#FF69B4", "tray_info_idx": "", "nozzle_id": 1}]
        right = [{"slot_id": 1, "type": "PETG", "color": "#FF69B4", "tray_info_idx": "", "nozzle_id": 0}]
        scheduler = _scheduler_with({2: left, 3: right})
        entries = (
            await _prepare(scheduler, {1: _printing(_loaded_ams(RED, BLUE, WHITE))}, [_next_job(2), _next_job(3)])
        )[1]
        assert [e.item_id for e in entries] == [2, 3]


class TestPrintAnyway:
    @pytest.mark.asyncio
    async def test_a_job_that_skips_the_filament_check_gets_no_line_but_keeps_its_trays(self):
        # The print uses tray 3; the job that prints anyway maps red on tray 0.
        ams = _loaded_ams(RED, BLUE, WHITE, GREEN)
        scheduler = _scheduler_with({2: RED_PINK, 3: RED_CYAN})
        jobs = [_next_job(2, skip_filament_check=True), _next_job(3)]
        (entry,) = (await _prepare(scheduler, {1: _printing(ams, mapping=(3,))}, jobs))[1]
        assert (entry.item_id, entry.position) == (3, 1)
        assert _slots(entry) == [(0, 1), (0, 2)]


class TestRack:
    @pytest.mark.asyncio
    async def test_a_paused_rack_printer_keeps_the_slots_its_layout_resolves(self):
        # An H3C reports its AMS 3H as unit 32 and tray_tar / tray_pre as the raw slot 0-8.
        ams = [
            {"id": 32, "tray": [_tray(i, "PLA", c) for i, c in enumerate((RED, BLUE, WHITE, GREEN, "FF69B4", CYAN))]}
        ]
        status = _status(ams, state="PAUSE", print_ams_mapping=[28], tray_now=28, tray_tar=5, tray_pre=4)
        scheduler = _scheduler_with({2: RED_PINK})
        (entry,) = (await _prepare(scheduler, {1: status}, [_next_job(2)]))[1]
        # Slots 4 and 5 are the print's (global 32 and 33), slot 0 is its own.
        assert _slots(entry) == [(32, 1), (32, 2), (32, 3)]


class TestPrintAnywayMemo:
    @pytest.mark.asyncio
    async def test_print_anyway_between_two_passes_removes_the_line(self):
        scheduler = _scheduler_with({2: RED_PINK})
        statuses = {1: _printing(_loaded_ams(RED, BLUE, WHITE))}
        job = _next_job(2)
        assert [e.item_id for e in (await _prepare(scheduler, statuses, [job]))[1]] == [2]
        job.skip_filament_check = True
        assert await _prepare(scheduler, statuses, [job]) == {}


class TestStepCost:
    @pytest.mark.asyncio
    async def test_only_the_first_eight_held_jobs_are_mapped(self):
        scheduler = _scheduler_with({i: _need(RED) for i in range(2, 22)})
        scheduler._planned_mapping = AsyncMock(wraps=scheduler._planned_mapping)
        jobs = [_next_job(i) for i in range(2, 22)] + [_next_job(30)]
        scheduler._get_filament_requirements.side_effect = lambda db, item: _need(RED) if item.id < 30 else RED_PINK
        holds = {i: [FilamentHold(i, 1, None, (PINK,))] for i in range(2, 22)}
        await _prepare(scheduler, {1: _status(_loaded_ams(RED, BLUE, WHITE))}, jobs, holds)
        assert scheduler._planned_mapping.await_count == 8 + 1

    @pytest.mark.asyncio
    async def test_nobody_holding_or_printing_costs_no_query(self):
        db = MagicMock()
        db.execute = AsyncMock(side_effect=AssertionError("queried"))
        scheduler = _scheduler_with({2: RED_PINK})
        scheduler._could_go_by_item = AsyncMock(side_effect=AssertionError("asked"))
        assert await _prepare(scheduler, {1: _status(_loaded_ams(RED, BLUE))}, [_next_job(2)], db=db) == {}
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_the_printers_a_job_could_go_to_come_from_the_slot_hint_step(self):
        scheduler = _scheduler_with({2: RED_PINK})
        scheduler._could_go_by_item = AsyncMock(side_effect=AssertionError("asked again"))
        entries = await _prepare(
            scheduler,
            {1: _printing(_loaded_ams(RED, BLUE, WHITE))},
            [_next_job(2)],
            shared={"could_go": {2: {1}}},
        )
        assert [e.item_id for e in entries[1]] == [2]

    @pytest.mark.asyncio
    async def test_only_the_first_eight_candidates_are_mapped_and_their_files_read(self):
        scheduler = _scheduler_with({i: _need(RED) for i in range(2, 22)})
        scheduler._planned_mapping = AsyncMock(wraps=scheduler._planned_mapping)
        scheduler._source_file_identities = AsyncMock(return_value={})
        jobs = [_next_job(i) for i in range(2, 22)]
        await _prepare(scheduler, {1: _printing(_loaded_ams(RED, BLUE, WHITE))}, jobs)
        assert scheduler._planned_mapping.await_count == 8
        (_db, read) = scheduler._source_file_identities.await_args.args
        assert [job.id for job in read] == list(range(2, 10))

    @pytest.mark.asyncio
    async def test_a_printer_that_leaves_the_step_is_no_longer_warned_about(self):
        scheduler = _scheduler_with({2: RED_PINK})
        scheduler._hint_warned = {1, (1, "prepare"), (2, "prepare")}
        await _prepare(scheduler, {1: _printing(_loaded_ams(RED, BLUE, WHITE))}, [])
        # The slot hint warnings are the other step's.
        assert scheduler._hint_warned == {1}

    @pytest.mark.asyncio
    async def test_a_failing_printer_stays_warned_about(self):
        scheduler = _scheduler_with({2: RED_PINK})
        scheduler._planned_mapping = AsyncMock(side_effect=RuntimeError("boom"))
        scheduler._prepare_for_printer = AsyncMock(side_effect=RuntimeError("boom"))
        await _prepare(scheduler, {1: _printing(_loaded_ams(RED, BLUE, WHITE))}, [_next_job(2)])
        assert scheduler._hint_warned == {(1, "prepare")}


class TestScheduledJobs:
    @pytest.mark.asyncio
    async def test_a_future_job_due_before_the_print_ends_gets_a_line(self):
        ams = _loaded_ams(RED, BLUE)
        soon = _job(2, scheduled_time=datetime.now(timezone.utc) + timedelta(minutes=5), manual_start=False)
        later = _job(3, scheduled_time=datetime.now(timezone.utc) + timedelta(hours=5), manual_start=False)
        scheduler = _scheduler_with({2: RED_PINK, 3: RED_PINK})
        status = _printing(ams, remaining_time=60)
        entries = await _prepare(scheduler, {1: status}, [soon, later])
        assert [e.item_id for e in entries[1]] == [2]

    @pytest.mark.asyncio
    async def test_a_future_job_is_skipped_when_the_remaining_time_is_unknown(self):
        ams = _loaded_ams(RED, BLUE)
        soon = _job(2, scheduled_time=datetime.now(timezone.utc) + timedelta(minutes=5), manual_start=False)
        scheduler = _scheduler_with({2: RED_PINK})
        assert await _prepare(scheduler, {1: _printing(ams, remaining_time=0)}, [soon]) == {}


class TestMemo:
    @pytest.mark.asyncio
    async def test_an_unchanged_printer_is_not_mapped_again(self):
        ams = _loaded_ams(RED, BLUE, WHITE)
        scheduler = _scheduler_with({2: RED_PINK})
        statuses = {1: _printing(ams)}
        jobs = [_next_job(2)]
        first = await _prepare(scheduler, statuses, jobs)
        planned = AsyncMock(side_effect=AssertionError("mapped again"))
        scheduler._planned_mapping = planned
        again = await _prepare(scheduler, statuses, jobs)
        assert again == first
        planned.assert_not_called()
        assert (1, "prepare") in scheduler._hint_memo

    @pytest.mark.asyncio
    async def test_a_changed_input_recomputes(self):
        ams = _loaded_ams(RED, BLUE, WHITE)
        jobs = [_next_job(2), _next_job(3)]
        paused = {"state": "PAUSE", "print_ams_mapping": [0], "tray_now": 0}
        cases = {
            "a slot": (_printing(_loaded_ams(RED, BLUE, GREEN)), jobs, None),
            "the print's mapping": (_printing(ams, mapping=(2,)), jobs, None),
            "the backup setting": (_printing(ams, ams_filament_backup=False), jobs, None),
            "the job order": (_printing(ams), [jobs[1], jobs[0]], None),
            "the state": (_status(ams, **paused), jobs, None),
            "tray_tar": (_status(ams, tray_tar=2, **paused), jobs, None),
            "tray_pre": (_status(ams, tray_pre=2, **paused), jobs, None),
            "the queue row's mapping": (_printing(ams, mapping=()), jobs, {1: {2}}),
        }
        for name, (status, order, rows) in cases.items():
            scheduler = _scheduler_with({2: RED_PINK, 3: RED_CYAN})
            if rows is None:
                await _prepare(scheduler, {1: _printing(ams)}, jobs)
            else:
                await _prepare(scheduler, {1: _printing(ams, mapping=())}, jobs, running_rows={1: {1}})
            if name in ("tray_tar", "tray_pre"):
                await _prepare(scheduler, {1: _status(ams, **paused)}, jobs)
            scheduler._planned_mapping = AsyncMock(wraps=scheduler._planned_mapping)
            await _prepare(scheduler, {1: status}, order, running_rows=rows)
            assert scheduler._planned_mapping.called, f"{name} did not recompute"

    @pytest.mark.asyncio
    async def test_a_degraded_result_is_not_kept(self):
        ams = _loaded_ams(RED, BLUE, WHITE)
        scheduler = _scheduler_with({2: None, 3: RED_PINK})
        await _prepare(scheduler, {1: _printing(ams)}, [_next_job(2), _next_job(3)])
        assert (1, "prepare") not in scheduler._hint_memo

    @pytest.mark.asyncio
    async def test_a_printer_that_has_nothing_to_prepare_leaves_no_memo(self):
        scheduler = _scheduler_with({})
        await _prepare(scheduler, {1: _printing(_loaded_ams(RED))}, [])
        assert scheduler._hint_memo == {}

    @pytest.mark.asyncio
    async def test_a_failing_printer_does_not_stop_the_others(self):
        ams = _loaded_ams(RED, BLUE, WHITE)
        scheduler = _scheduler_with({2: RED_PINK, 3: RED_PINK})
        original = scheduler._planned_mapping

        async def planned(db, item, printer_id, **kw):
            if printer_id == 1:
                raise RuntimeError("boom")
            return await original(db, item, printer_id, **kw)

        scheduler._planned_mapping = planned
        entries = await _prepare(
            scheduler, {1: _printing(ams), 2: _printing(ams)}, [_next_job(2), _next_job(3, printer_id=2)]
        )
        assert 2 in entries


class TestInThePass:
    async def _pass(self, ctx, scheduler, status, idle=lambda pid, *_: False):
        """One queue pass; ``status`` is one printer's (printer 1) or a dict of them by printer id."""
        statuses = status if isinstance(status, dict) else {1: status}
        patches = [
            patch("backend.app.services.print_scheduler.async_session", ctx.session_maker),
            patch("backend.app.core.database.async_session", ctx.session_maker),
            patch("backend.app.services.print_scheduler.printer_manager.is_connected", MagicMock(return_value=True)),
            patch(
                "backend.app.services.print_scheduler.printer_manager.get_status",
                MagicMock(side_effect=lambda pid: statuses.get(pid)),
            ),
            patch(
                "backend.app.services.print_scheduler.printer_manager.get_all_statuses",
                MagicMock(return_value=statuses),
            ),
            patch(
                "backend.app.services.print_scheduler.ha_sensor_manager.blocked_printers",
                AsyncMock(return_value={}),
            ),
            patch("backend.app.services.notification_service.notification_service.on_queue_job_waiting", AsyncMock()),
            patch("backend.app.services.print_scheduler.compute_deficit_for_queue_item", AsyncMock(return_value=[])),
            patch.object(scheduler, "_is_printer_idle", MagicMock(side_effect=idle)),
            patch.object(scheduler, "_check_auto_drying", AsyncMock()),
            patch.object(scheduler, "_launch_uploads", MagicMock()),
        ]
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            await scheduler.check_queue()

    @pytest.mark.asyncio
    async def test_a_printing_printer_gets_its_lines_without_any_hold(self, queue_db):
        await _add_item(queue_db, printer_id=1, target_model=None, status="printing", position=1)
        job = await _add_item(queue_db, printer_id=1, target_model=None, position=2)
        scheduler = _scheduler_with({job: RED_PINK})
        await self._pass(queue_db, scheduler, _printing(_loaded_ams(RED, BLUE, WHITE)))
        assert scheduler.filament_holds_snapshot() == {}
        (entry,) = scheduler.prepare_snapshot()[1]
        assert (entry.item_id, [s.tray_id for s in entry.hint.slots]) == (job, [1, 2])
        assert (1, "prepare") in scheduler._hint_memo

        async with queue_db.session_maker() as db:
            await db.execute(delete(PrintQueueItem).where(PrintQueueItem.id == job))
            await db.commit()
        await self._pass(queue_db, scheduler, _printing(_loaded_ams(RED, BLUE, WHITE)))
        assert scheduler.prepare_snapshot() == {}

    @pytest.mark.asyncio
    async def test_the_mapping_of_the_running_queue_row_is_used(self, queue_db):
        await _add_item(
            queue_db, printer_id=1, target_model=None, status="printing", position=1, ams_mapping=json.dumps([2])
        )
        job = await _add_item(queue_db, printer_id=1, target_model=None, position=2)
        scheduler = _scheduler_with({job: RED_PINK})
        await self._pass(queue_db, scheduler, _printing(_loaded_ams(RED, BLUE, WHITE), mapping=()))
        (entry,) = scheduler.prepare_snapshot()[1]
        assert [s.tray_id for s in entry.hint.slots] == [1]

    @pytest.mark.asyncio
    async def test_a_failing_step_does_not_touch_the_pass(self, queue_db):
        await _add_item(queue_db, printer_id=1, target_model=None, status="printing", position=1)
        await _add_item(queue_db, printer_id=1, target_model=None, position=2)
        scheduler = _scheduler_with({})
        scheduler._compute_prepare = AsyncMock(side_effect=RuntimeError("boom"))
        await self._pass(queue_db, scheduler, _printing(_loaded_ams(RED)))
        assert scheduler.prepare_snapshot() == {}

    @pytest.mark.asyncio
    async def test_a_pass_that_stops_early_keeps_the_last_lines(self, queue_db):
        scheduler = _scheduler_with({})
        kept = (MagicMock(),)
        scheduler._prepare = {1: kept}
        with (
            patch.object(scheduler, "_check_queue_pass", AsyncMock(side_effect=RuntimeError("boom"))),
            pytest.raises(RuntimeError),
        ):
            await scheduler.check_queue()
        assert scheduler.prepare_snapshot() == {1: kept}

    async def _two_printers(self, queue_db):
        """Printer 1 is idle and holds a job that needs red PLA (it has PETG and an empty slot); printer 2 prints and has a next job."""
        held = await _add_item(queue_db, printer_id=1, target_model=None, position=1)
        await _add_item(queue_db, printer_id=2, target_model=None, status="printing", position=1)
        job = await _add_item(queue_db, printer_id=2, target_model=None, position=2)
        scheduler = _scheduler_with({held: _need(RED), job: RED_PINK})
        loaded = [{"id": 0, "tray": [_tray(0, "PETG", BLUE), _tray(1, exists=False)]}]
        statuses = {1: _status(loaded), 2: _printing(_loaded_ams(RED, BLUE, WHITE))}
        return scheduler, statuses, held, job

    @pytest.mark.asyncio
    async def test_a_failing_hint_step_keeps_the_prepare_lines(self, queue_db):
        scheduler, statuses, held, job = await self._two_printers(queue_db)
        scheduler._compute_slot_hints = AsyncMock(side_effect=RuntimeError("boom"))
        await self._pass(queue_db, scheduler, statuses, idle=lambda pid, *_: pid == 1)
        assert scheduler.slot_hints_snapshot() == {}
        (entry,) = scheduler.prepare_snapshot()[2]
        assert entry.item_id == job
        assert (2, "prepare") in scheduler._hint_memo

    @pytest.mark.asyncio
    async def test_a_failing_prepare_step_keeps_the_slot_hints(self, queue_db):
        scheduler, statuses, held, job = await self._two_printers(queue_db)
        scheduler._compute_prepare = AsyncMock(side_effect=RuntimeError("boom"))
        await self._pass(queue_db, scheduler, statuses, idle=lambda pid, *_: pid == 1)
        assert scheduler.prepare_snapshot() == {}
        assert scheduler.slot_hints_snapshot()[1].state == HINT_FREE
        assert 1 in scheduler._hint_memo
        assert (2, "prepare") not in scheduler._hint_memo

    @pytest.mark.asyncio
    async def test_both_steps_give_their_result_in_one_pass(self, queue_db):
        scheduler, statuses, held, job = await self._two_printers(queue_db)
        scheduler._could_go_by_item = AsyncMock(wraps=scheduler._could_go_by_item)
        await self._pass(queue_db, scheduler, statuses, idle=lambda pid, *_: pid == 1)
        assert 1 in scheduler.slot_hints_snapshot()
        assert [e.item_id for e in scheduler.prepare_snapshot()[2]] == [job]
        # The printers each job could go to are asked once for both steps.
        assert scheduler._could_go_by_item.await_count == 1


def _slot_dict(tray_id, material="PLA", color="#FF0000", empty=False):
    return {
        "ams_id": 0,
        "tray_id": tray_id,
        "global_tray_id": tray_id,
        "is_ht": False,
        "is_external": False,
        "ams_type": 1,
        "extruder_id": None,
        "type": "" if empty else material,
        "color": "" if empty else color,
        "tray_info_idx": "",
        "tray_sub_brands": "",
        "empty": empty,
        "nozzle": None,
    }


def _hs(tray_id, material="PLA", color="#FF0000"):
    return HintSlot(0, tray_id, False, False, 1, None, material, color)


class TestPrepareNeverOffersWhatFitsItsOwnFilament:
    RED_F = TodoFilament("PLA", "#FF0000", "Red")

    def test_settled_hint_drops_fitting_slots_and_the_state_follows(self):
        hint = SlotHint(
            1, HINT_REPLACEABLE, (_hs(0), _hs(1, color="#0000FF")), loaded=(_hs(0), _hs(1, color="#0000FF"))
        )
        assert [s.tray_id for s in settled_hint(hint, (self.RED_F,)).slots] == [1]
        only = SlotHint(1, HINT_REPLACEABLE, (_hs(0),), loaded=(_hs(0),))
        assert (settled_hint(only, (self.RED_F,)).state, settled_hint(only, (self.RED_F,)).slots) == (
            HINT_ALL_NEEDED,
            (),
        )

    def test_a_prepare_line_does_not_offer_a_tray_that_fits_its_filament(self):
        hint = SlotHint(1, HINT_REPLACEABLE, (_hs(0), _hs(1, color="#0000FF")))
        shown = _hint_dict(hint, (self.RED_F,), {})
        assert [s["tray_id"] for s in shown["slots"]] == [1]

    def test_a_claim_skips_a_tray_that_fits_its_filament(self):
        scheduler = _scheduler_with({})
        slots = [_slot_dict(0), _slot_dict(1, color="#0000FF"), _slot_dict(2, empty=True)]
        hint = SlotHint(1, HINT_FREE, (_hs(2, "", ""),), loaded=(_hs(0), _hs(1, color="#0000FF")))
        # Two missing red filaments: the free slot, then the first loaded slot that is not red.
        two = (self.RED_F, TodoFilament("PLA", "#FF0000", "Red", nozzle=None, no_stock=True))
        assert scheduler._claimed_trays(hint, two, slots, set()) == {1, 2}

    def test_a_short_filament_claims_no_free_slot(self):
        scheduler = _scheduler_with({})
        slots = [_slot_dict(0), _slot_dict(1, empty=True)]
        hint = SlotHint(1, HINT_FREE, (_hs(1, "", ""),), loaded=(_hs(0),))
        short = TodoFilament(
            "PLA", "#FF0000", "Red", short=True, short_trays=(ShortTray(0, 0, 5.0),), required_grams=30.0
        )
        assert scheduler._claimed_trays(hint, (short,), slots, set()) == set()
        # A missing filament next to it still claims its own.
        other = TodoFilament("PETG", "#FF69B4", "Pink")
        assert scheduler._claimed_trays(hint, (short, other), slots, set()) == {1}

    @pytest.mark.asyncio
    async def test_a_held_short_filament_keeps_the_next_jobs_free_slots(self):
        ams = [{"id": 0, "tray": [_tray(0, "PLA", RED), _tray(1, "PLA", BLUE), _tray(2, exists=False)]}]
        scheduler = _scheduler_with({2: _need(RED), 3: RED_PINK})
        short = TodoFilament(
            "PLA", "#" + RED, "Red", short=True, short_trays=(ShortTray(0, 0, 5.0),), required_grams=30.0
        )
        holds = {2: [FilamentHold(2, 1, None, (short,))]}
        (entry,) = (await _prepare(scheduler, {1: _status(ams)}, [_next_job(2), _next_job(3)], holds))[1]
        assert entry.item_id == 3
        assert (entry.hint.state, _slots(entry)) == (HINT_FREE, [(0, 2)])

    @pytest.mark.asyncio
    async def test_held_short_rows_stay_apart_and_claim_only_the_missing_one(self):
        ams = [
            {
                "id": 0,
                "tray": [_tray(0, "PLA", RED), _tray(1, "PLA", RED), _tray(2, exists=False), _tray(3, exists=False)],
            }
        ]
        scheduler = _scheduler_with({2: _req(("PLA", RED), ("PETG", "FF69B4")), 3: RED_CYAN})
        red = "#" + RED
        rows = (
            TodoFilament("PLA", red, "Red", short=True, short_trays=(ShortTray(0, 0, 5.0),)),
            TodoFilament("PLA", red, "Red", short=True, short_trays=(ShortTray(0, 1, 6.0),)),
            PINK,
        )
        holds = {2: [FilamentHold(2, 1, None, rows)]}
        (entry,) = (await _prepare(scheduler, {1: _status(ams)}, [_next_job(2), _next_job(3)], holds))[1]
        assert (entry.item_id, _slots(entry)) == (3, [(0, 3)])
