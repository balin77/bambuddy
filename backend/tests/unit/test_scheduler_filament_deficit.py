"""Scheduler pre-dispatch filament-deficit guard tests (#1496).

``PrintScheduler._block_on_filament_deficit`` is the gate that keeps an
auto_dispatch=True VP intake (or any other scheduler-driven dispatch) from
sending a print onto a spool that can't satisfy it. On a deficit it
promotes the item to manual_start; when a previously-flagged item's spool
is now adequate it clears the flag so the next tick dispatches.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from backend.app.models.print_queue import PrintQueueItem
from backend.app.services.filament_deficit import FilamentDeficit, describe_deficit
from backend.app.services.print_scheduler import PrintScheduler, _describe_deficit_for_notification
from backend.app.services.queue_todo import ShortTray, TodoFilament


@pytest.fixture
def scheduler():
    """A fresh scheduler instance — internal state is not exercised."""
    return PrintScheduler()


@pytest.fixture
def queue_item(db_session, printer_factory):
    """Helper to drop a queue item the helper can mutate."""

    async def _make(**overrides):
        printer = await printer_factory()
        defaults = {
            "printer_id": printer.id,
            "status": "pending",
            "manual_start": False,
            "filament_short": False,
        }
        defaults.update(overrides)
        item = PrintQueueItem(**defaults)
        db_session.add(item)
        await db_session.commit()
        await db_session.refresh(item)
        return item

    return _make


@pytest.mark.asyncio
async def test_blocks_on_deficit_promotes_to_manual_start(scheduler, db_session, queue_item):
    item = await queue_item()
    with patch(
        "backend.app.services.print_scheduler.compute_deficit_for_queue_item",
        AsyncMock(
            return_value=[
                FilamentDeficit(
                    slot_id=1,
                    ams_id=0,
                    tray_id=0,
                    filament_type="PLA",
                    required_grams=270.0,
                    remaining_grams=200.0,
                ),
            ]
        ),
    ):
        blocked = await scheduler._block_on_filament_deficit(db_session, item)

    assert blocked is True
    await db_session.refresh(item)
    assert item.manual_start is True
    assert item.filament_short is True


@pytest.mark.asyncio
async def test_clears_stale_flag_when_deficit_resolves(scheduler, db_session, queue_item):
    """Previously-flagged item whose spool was swapped is unblocked."""
    item = await queue_item(filament_short=True, manual_start=False)
    with patch(
        "backend.app.services.print_scheduler.compute_deficit_for_queue_item",
        AsyncMock(return_value=[]),
    ):
        blocked = await scheduler._block_on_filament_deficit(db_session, item)

    assert blocked is False
    await db_session.refresh(item)
    assert item.filament_short is False
    assert item.manual_start is False


@pytest.mark.asyncio
async def test_no_deficit_no_op(scheduler, db_session, queue_item):
    """Happy path — no deficit, no flag changes, dispatch proceeds."""
    item = await queue_item()
    with patch(
        "backend.app.services.print_scheduler.compute_deficit_for_queue_item",
        AsyncMock(return_value=[]),
    ):
        blocked = await scheduler._block_on_filament_deficit(db_session, item)

    assert blocked is False
    await db_session.refresh(item)
    assert item.filament_short is False
    assert item.manual_start is False


@pytest.mark.asyncio
async def test_helper_exception_does_not_wedge_dispatch(scheduler, db_session, queue_item):
    """A flaky deficit check (e.g. Spoolman timeout) must not block dispatch."""
    item = await queue_item()
    with patch(
        "backend.app.services.print_scheduler.compute_deficit_for_queue_item",
        AsyncMock(side_effect=RuntimeError("network down")),
    ):
        blocked = await scheduler._block_on_filament_deficit(db_session, item)

    assert blocked is False
    await db_session.refresh(item)
    assert item.filament_short is False


@pytest.mark.asyncio
async def test_skip_filament_check_short_circuits_without_compute(scheduler, db_session, queue_item):
    """User clicked Print Anyway (skip_filament_check=True): no compute, no flag (#1698-followup).

    Pre-fix the scheduler re-ran the deficit check on every tick, re-set
    manual_start/filament_short to True, and the item bounced between
    "user said anyway" (route clears flags) and "scheduler re-blocked"
    forever. With the persistent acknowledgement flag the scheduler bails
    early without even touching the deficit helper.
    """
    item = await queue_item(skip_filament_check=True)
    compute_mock = AsyncMock(
        return_value=[
            FilamentDeficit(
                slot_id=1,
                ams_id=0,
                tray_id=0,
                filament_type="PLA",
                required_grams=270.0,
                remaining_grams=200.0,
            ),
        ]
    )
    with patch(
        "backend.app.services.print_scheduler.compute_deficit_for_queue_item",
        compute_mock,
    ):
        blocked = await scheduler._block_on_filament_deficit(db_session, item)

    assert blocked is False
    compute_mock.assert_not_awaited()
    await db_session.refresh(item)
    # Flags must not get re-set by the scheduler now that the user has
    # acknowledged the deficit.
    assert item.filament_short is False
    assert item.manual_start is False


@pytest.mark.asyncio
async def test_the_waiting_notification_names_the_printer(scheduler, db_session, queue_item):
    """A channel limited to the job's printer is told the job is short."""
    item = await queue_item()
    waiting = AsyncMock()
    deficit = FilamentDeficit(
        slot_id=1, ams_id=0, tray_id=0, filament_type="PLA", required_grams=270.0, remaining_grams=200.0
    )
    with (
        patch("backend.app.services.print_scheduler.compute_deficit_for_queue_item", AsyncMock(return_value=[deficit])),
        patch("backend.app.services.notification_service.notification_service.on_queue_job_waiting", waiting),
    ):
        await scheduler._block_on_filament_deficit(db_session, item)

    assert waiting.await_args.kwargs["printer_id"] == item.printer_id


def _deficit(ams_id, tray_id, remaining, required=40.0, material="PLA", slot_id=1, pooled=()):
    return FilamentDeficit(
        slot_id=slot_id,
        ams_id=ams_id,
        tray_id=tray_id,
        filament_type=material,
        required_grams=required,
        remaining_grams=remaining,
        pooled=pooled,
    )


def _short_filament(deficits, color_name=""):
    """The To do list's object for ``deficits``: what the sentence is worded from."""
    facts = describe_deficit(deficits, color_name=color_name)
    return TodoFilament(
        type=facts.filament_type,
        color="",
        color_name=color_name,
        short=True,
        short_trays=facts.trays,
        required_grams=facts.required_grams,
    )


async def _waiting_reason_sent(scheduler, db_session, item, deficits):
    """The waiting_reason the notification gets for ``deficits`` (#3642)."""
    notify = AsyncMock()
    with (
        patch("backend.app.services.print_scheduler.compute_deficit_for_queue_item", AsyncMock(return_value=deficits)),
        patch("backend.app.services.print_scheduler.notification_service.on_queue_job_waiting", notify),
    ):
        assert await scheduler._block_on_filament_deficit(db_session, item) is True
    return notify.await_args.kwargs["waiting_reason"]


@pytest.mark.asyncio
async def test_notification_reason_is_a_sentence_not_the_code(scheduler, db_session, queue_item):
    item = await queue_item()
    reason = await _waiting_reason_sent(scheduler, db_session, item, [_deficit(0, 1, 12.0)])

    # The To do list's sentence, with the printer the notification adds.
    assert reason == "Not enough PLA on Test Printer: A2 has 12 g, the job needs 40 g"
    assert "filament_short" not in reason


@pytest.mark.asyncio
async def test_notification_reason_with_unknown_grams(scheduler, db_session, queue_item):
    item = await queue_item()
    reason = await _waiting_reason_sent(scheduler, db_session, item, [_deficit(0, 0, None)])

    assert reason == "Not enough PLA in A1 on Test Printer"


@pytest.mark.asyncio
async def test_notification_reason_joins_several_deficits(scheduler, db_session, queue_item):
    item = await queue_item()
    reason = await _waiting_reason_sent(
        scheduler,
        db_session,
        item,
        [_deficit(0, 1, 12.0), _deficit(1, 3, 50.0, 90.0, "PETG", slot_id=2)],
    )

    assert reason == (
        "Not enough filament on Test Printer: PLA A2 has 12 g, the job needs 40 g; PETG B4 has 50 g, the job needs 90 g"
    )


@pytest.mark.asyncio
async def test_notification_reason_pools_the_spools_of_one_filament(scheduler, db_session, queue_item):
    """AMS Filament Backup: A2 + A3 count together, as in the To do list."""
    item = await queue_item()
    pooled = ((0, 1, 10.0), (0, 2, 15.0))
    reason = await _waiting_reason_sent(
        scheduler,
        db_session,
        item,
        [_deficit(0, 1, 10.0, pooled=pooled), _deficit(0, 2, 15.0, slot_id=2, pooled=pooled)],
    )

    assert reason == "Not enough PLA on Test Printer: A2 + A3 have 25 g, the job needs 80 g"


@pytest.mark.asyncio
async def test_notification_reason_names_ht_and_external_slots(scheduler, db_session, queue_item):
    item = await queue_item()
    reason = await _waiting_reason_sent(
        scheduler, db_session, item, [_deficit(128, 0, 5.0), _deficit(255, 1, 8.0, material="PETG", slot_id=2)]
    )

    assert "PLA HT-A has 5 g, the job needs 40 g" in reason
    assert "PETG Ext-R has 8 g, the job needs 40 g" in reason


@pytest.mark.asyncio
async def test_notification_reason_names_the_colour_of_the_job(scheduler, db_session, queue_item):
    """The colour name comes from the job's requirement for the slot, as in the To do list."""
    item = await queue_item()
    requirements = [{"slot_id": 1, "type": "PLA", "color": "#C62828", "color_name": "Lava Red"}]
    with patch.object(scheduler, "_get_filament_requirements", AsyncMock(return_value=requirements)):
        reason = await _waiting_reason_sent(scheduler, db_session, item, [_deficit(0, 1, 12.0)])

    assert reason == "Not enough PLA Lava Red on Test Printer: A2 has 12 g, the job needs 40 g"


def test_describe_deficit_for_notification_without_slot_or_printer():
    assert _describe_deficit_for_notification([_short_filament([_deficit(None, None, 12.0)])]) == "Not enough PLA"


def test_describe_deficit_for_notification_without_known_type():
    short = [_short_filament([_deficit(0, 1, 12.0, material="")])]

    assert (
        _describe_deficit_for_notification(short, "X1C")
        == "Not enough Filament on X1C: A2 has 12 g, the job needs 40 g"
    )


def test_describe_deficit_for_notification_leaves_out_an_unknown_job_amount():
    short = [TodoFilament(type="PLA", color="", short=True, short_trays=(ShortTray(0, 1, 12.0),))]

    assert _describe_deficit_for_notification(short) == "Not enough PLA: A2 has 12 g"


def test_describe_deficit_for_notification_groups_thousands():
    short = [
        TodoFilament(type="PLA", color="", short=True, short_trays=(ShortTray(0, 1, 1200.0),), required_grams=1500.0)
    ]

    assert _describe_deficit_for_notification(short) == "Not enough PLA: A2 has 1,200 g, the job needs 1,500 g"
