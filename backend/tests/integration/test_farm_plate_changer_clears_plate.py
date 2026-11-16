"""A job that clears its own plate spends a plate-changer plate (#3575, #3576).

Farm-only integration of both features: the count goes down exactly where the
plate-clear gate is lifted, i.e. a successful, positively matched queue job
with the flag on an "inherit" printer whose global setting asks for the
confirmation. Everything else keeps its old behaviour.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.app.models.print_queue import PrintQueueItem
from backend.app.models.printer import Printer
from backend.app.models.settings import Settings
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
    yield
    for marks in (plate_changer._count_pending, plate_changer._count_unknown):
        marks.clear()


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


async def _setup(db_session, qp, *, flag, override="inherit", capacity=5, remaining=3):
    printer = await db_session.get(Printer, qp["printer"])
    printer.plate_clear_override = override
    printer.plate_capacity = capacity
    printer.plates_remaining = remaining
    item = await db_session.get(PrintQueueItem, qp["item"])
    item.clears_plate = flag
    db_session.add(Settings(key="require_plate_clear", value="true"))
    await db_session.commit()


async def _remaining(db_session, printer_id):
    db_session.expire_all()
    return (await db_session.get(Printer, printer_id)).plates_remaining


async def test_flagged_job_on_inherit_printer_counts_and_lifts_gate(
    test_engine, db_session, queued_print, changer_mocks, gate
):
    await _setup(db_session, queued_print, flag=True)

    await _complete(test_engine, queued_print["printer"], "completed")

    assert await _remaining(db_session, queued_print["printer"]) == 2
    assert printer_manager.is_awaiting_plate_clear(queued_print["printer"]) is False
    changer_mocks[0].send_printer_plates_changed.assert_awaited_once_with(queued_print["printer"], 2, 5)


async def test_unflagged_job_on_inherit_printer_neither_counts_nor_lifts_gate(
    test_engine, db_session, queued_print, changer_mocks, gate
):
    await _setup(db_session, queued_print, flag=False)

    await _complete(test_engine, queued_print["printer"], "completed")

    assert await _remaining(db_session, queued_print["printer"]) == 3
    assert printer_manager.is_awaiting_plate_clear(queued_print["printer"]) is True
    changer_mocks[0].send_printer_plates_changed.assert_not_awaited()


async def test_flagged_job_on_always_require_printer_neither_counts_nor_lifts_gate(
    test_engine, db_session, queued_print, changer_mocks, gate
):
    await _setup(db_session, queued_print, flag=True, override="on")

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
