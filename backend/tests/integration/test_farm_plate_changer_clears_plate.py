"""A job that clears its own plate spends a plate-changer plate (#3575, #3576).

Farm-only integration of both features: the count goes down exactly where the
plate-clear gate is lifted, i.e. a successful, positively matched queue job
with the flag on a printer that follows the app setting (no require_plate_clear
of its own, #2860) while that setting asks for the confirmation. A printer whose
own setting is on wins over the flag; everything else keeps its old behaviour.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.app.models.print_queue import PrintQueueItem
from backend.app.models.printer import Printer
from backend.app.models.settings import Settings
from backend.app.services import plate_clear
from backend.app.services.printer_manager import printer_manager
from backend.tests.integration.test_print_complete_end_to_end import (  # noqa: F401
    _clean,
    _complete,
    _no_finish_photo,
    queued_print,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

PC = "backend.app.services.plate_changer"


@pytest.fixture(autouse=True)
def _clean_marks():
    from backend.app.services import plate_changer

    for marks in (plate_changer._count_pending, plate_changer._count_unknown):
        marks.clear()
    plate_clear.load_overrides({})
    yield
    for marks in (plate_changer._count_pending, plate_changer._count_unknown):
        marks.clear()
    plate_clear.load_overrides({})


@pytest.fixture
def changer_mocks():
    with patch(f"{PC}.ws_manager") as ws, patch(f"{PC}.notification_service") as notif:
        ws.send_printer_plates_changed = AsyncMock()
        notif.on_plate_changer_empty = AsyncMock()
        yield ws, notif


@pytest.fixture
def gate():
    """Spy on the plate-clear gate; it still records the flag like the real one."""

    def _set(printer_id, awaiting):
        if awaiting:
            printer_manager._awaiting_plate_clear.add(printer_id)
        else:
            printer_manager._awaiting_plate_clear.discard(printer_id)

    with patch.object(printer_manager, "set_awaiting_plate_clear", MagicMock(side_effect=_set)) as spy:
        yield spy
    printer_manager._awaiting_plate_clear.clear()


async def _setup(db_session, qp, *, flag, override=None, require_clear=True, capacity=5, remaining=3):
    """``override`` is the printer's own require_plate_clear, ``require_clear`` the app setting."""
    printer = await db_session.get(Printer, qp["printer"])
    printer.require_plate_clear = override
    # The printer routes keep the cache current; here the row is written directly.
    plate_clear.set_override(qp["printer"], override)
    printer.plate_capacity = capacity
    printer.plates_remaining = remaining
    item = await db_session.get(PrintQueueItem, qp["item"])
    item.clears_plate = flag
    db_session.add(Settings(key="require_plate_clear", value="true" if require_clear else "false"))
    await db_session.commit()


async def _remaining(db_session, printer_id):
    db_session.expire_all()
    return (await db_session.get(Printer, printer_id)).plates_remaining


async def test_flagged_job_on_a_printer_following_the_setting_counts_and_lifts_gate(
    test_engine, db_session, queued_print, changer_mocks, gate
):
    await _setup(db_session, queued_print, flag=True)

    await _complete(test_engine, queued_print["printer"], "completed")

    assert await _remaining(db_session, queued_print["printer"]) == 2
    assert printer_manager.is_awaiting_plate_clear(queued_print["printer"]) is False
    changer_mocks[0].send_printer_plates_changed.assert_awaited_once_with(queued_print["printer"], 2, 5)


async def test_unflagged_job_on_a_printer_following_the_setting_neither_counts_nor_lifts_gate(
    test_engine, db_session, queued_print, changer_mocks, gate
):
    await _setup(db_session, queued_print, flag=False)

    await _complete(test_engine, queued_print["printer"], "completed")

    assert await _remaining(db_session, queued_print["printer"]) == 3
    assert printer_manager.is_awaiting_plate_clear(queued_print["printer"]) is True
    changer_mocks[0].send_printer_plates_changed.assert_not_awaited()


async def test_flagged_job_on_a_printer_whose_own_setting_is_on_neither_counts_nor_lifts_gate(
    test_engine, db_session, queued_print, changer_mocks, gate
):
    await _setup(db_session, queued_print, flag=True, override=True)

    await _complete(test_engine, queued_print["printer"], "completed")

    assert await _remaining(db_session, queued_print["printer"]) == 3
    assert printer_manager.is_awaiting_plate_clear(queued_print["printer"]) is True
    changer_mocks[0].send_printer_plates_changed.assert_not_awaited()


@pytest.mark.parametrize("status", ["failed", "aborted", "cancelled"])
async def test_flagged_job_that_did_not_succeed_neither_counts_nor_lifts_gate(
    test_engine, db_session, queued_print, changer_mocks, gate, status
):
    await _setup(db_session, queued_print, flag=True)

    await _complete(test_engine, queued_print["printer"], status)

    assert await _remaining(db_session, queued_print["printer"]) == 3
    assert printer_manager.is_awaiting_plate_clear(queued_print["printer"]) is True


@pytest.mark.parametrize(
    ("override", "require_clear", "flag", "held", "counted"),
    [
        # Follows the app setting, and that asks: only the flag clears the plate.
        (None, True, False, True, False),
        (None, True, True, False, True),
        # Follows the app setting, and that is off: nobody confirms, flag or not.
        (None, False, False, False, True),
        (None, False, True, False, True),
        # The printer's own setting is on: it wins over the flag and the app setting.
        (True, True, False, True, False),
        (True, True, True, True, False),
        (True, False, False, True, False),
        (True, False, True, True, False),
        # The printer's own setting is off: it clears its plate itself.
        (False, True, False, False, True),
        (False, True, True, False, True),
        (False, False, False, False, True),
        (False, False, True, False, True),
    ],
)
async def test_truth_table_of_a_successful_finish(
    test_engine, db_session, queued_print, changer_mocks, gate, override, require_clear, flag, held, counted
):
    """The queue is held and a plate is spent on opposite sides of one rule (#2860, #3575, #3576)."""
    from backend.app.services.print_scheduler import _plate_clear_holds

    await _setup(db_session, queued_print, flag=flag, override=override, require_clear=require_clear)

    await _complete(test_engine, queued_print["printer"], "completed")

    assert _plate_clear_holds(queued_print["printer"], require_clear) is held
    assert await _remaining(db_session, queued_print["printer"]) == (2 if counted else 3)
    assert held is not counted
