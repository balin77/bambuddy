"""Every action of the To do list is refused for a printer outside the caller's scope (#3726).

The list offers its actions in place: assign a spool (built-in inventory or
Spoolman), switch a printer's plug on again, edit a job or move it to another
printer. Each is an existing route, so the scope of #1727 applies as it does
on the Printers and Queue pages: a member of a group limited to some printers
gets the same 404 a missing printer gets, and nothing is written.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from backend.app.models.print_queue import PrintQueueItem
from backend.app.models.spool import Spool
from backend.app.models.spool_assignment import SpoolAssignment
from backend.app.models.spoolman_slot_assignment import SpoolmanSlotAssignment
from backend.tests.integration.test_printer_scope_1727 import _admin_token, _auth, _group, _user

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

# What the To do actions need, nothing printer-wide beyond reading the lists.
TODO_PERMISSIONS = [
    "queue:read_all",
    "queue:update_all",
    "inventory:update",
    "smart_plugs:read",
    "smart_plugs:control",
    "printers:read",
]


async def _member(client: AsyncClient, printer_ids: list[int]) -> dict[str, str]:
    """A user with the To do permissions whose team group is limited to ``printer_ids``."""
    admin = await _admin_token(client)
    perms = await _group(client, admin, "todo_perms", permissions=TODO_PERMISSIONS)
    team = await _group(client, admin, "todo_team", printer_ids=printer_ids)
    return _auth((await _user(client, admin, "todo_member", [perms, team]))[0])


@pytest.fixture
async def two_printers(printer_factory):
    """(in scope, out of scope)"""
    return await printer_factory(name="Mine"), await printer_factory(name="Theirs")


async def _queue_item(db, archive_factory, printer_id: int, position: int = 1) -> PrintQueueItem:
    archive = await archive_factory(printer_id, print_name="Lamp")
    item = PrintQueueItem(archive_id=archive.id, printer_id=printer_id, status="pending", position=position)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


async def test_the_inventory_assign_is_refused_for_another_teams_printer(
    async_client: AsyncClient, db_session, two_printers
):
    mine, theirs = two_printers
    spool = Spool(material="PLA", label_weight=1000, weight_used=0)
    db_session.add(spool)
    await db_session.commit()
    member = await _member(async_client, [mine.id])

    response = await async_client.post(
        "/api/v1/inventory/assignments",
        headers=member,
        json={"spool_id": spool.id, "printer_id": theirs.id, "ams_id": 0, "tray_id": 2},
    )

    assert response.status_code == 404, response.text
    assert response.json()["detail"] == "Printer not found"
    assert (await db_session.execute(select(SpoolAssignment))).scalars().all() == []


async def test_the_spoolman_slot_assign_is_refused_for_another_teams_printer(
    async_client: AsyncClient, db_session, two_printers
):
    from backend.app.models.settings import Settings

    mine, theirs = two_printers
    db_session.add_all(
        [Settings(key="spoolman_enabled", value="true"), Settings(key="spoolman_url", value="http://localhost:7912")]
    )
    await db_session.commit()
    client = MagicMock()
    client.base_url = "http://localhost:7912"
    client.get_spool = AsyncMock(return_value={"id": 10, "archived": False, "extra": {}})
    member = await _member(async_client, [mine.id])

    with patch("backend.app.api.routes.spoolman_inventory._get_client", AsyncMock(return_value=client)):
        response = await async_client.post(
            "/api/v1/spoolman/inventory/slot-assignments",
            headers=member,
            json={"spoolman_spool_id": 10, "printer_id": theirs.id, "ams_id": 0, "tray_id": 2},
        )

    assert response.status_code == 404, response.text
    assert response.json()["detail"] == "Printer not found"
    # Refused before Spoolman was asked for the spool, and nothing was written.
    client.get_spool.assert_not_called()
    assert (await db_session.execute(select(SpoolmanSlotAssignment))).scalars().all() == []


async def test_switching_on_the_plug_of_another_teams_printer_is_refused(
    async_client: AsyncClient, two_printers, smart_plug_factory
):
    mine, theirs = two_printers
    plug = await smart_plug_factory(name="Theirs plug", printer_id=theirs.id)
    member = await _member(async_client, [mine.id])

    with patch("backend.app.api.routes.smart_plugs.tasmota_service.turn_on", AsyncMock(return_value=True)) as turn_on:
        control = await async_client.post(f"/api/v1/smart-plugs/{plug.id}/control", headers=member, json={"action": "on"})
    lookup = await async_client.get(f"/api/v1/smart-plugs/by-printer/{theirs.id}", headers=member)

    assert control.status_code == 404, control.text
    turn_on.assert_not_called()
    # The lookup that comes first in the button is refused the same way, and names no plug.
    assert lookup.status_code == 404, lookup.text
    assert "Theirs plug" not in lookup.text


async def test_editing_a_job_on_another_teams_printer_is_refused(
    async_client: AsyncClient, db_session, two_printers, archive_factory
):
    mine, theirs = two_printers
    item = await _queue_item(db_session, archive_factory, theirs.id)
    member = await _member(async_client, [mine.id])

    response = await async_client.patch(f"/api/v1/queue/{item.id}", headers=member, json={"auto_off_after": True})

    assert response.status_code == 404, response.text
    await db_session.refresh(item)
    assert item.auto_off_after is False


async def test_moving_a_job_to_another_teams_printer_is_refused(
    async_client: AsyncClient, db_session, two_printers, archive_factory
):
    mine, theirs = two_printers
    item = await _queue_item(db_session, archive_factory, mine.id)
    member = await _member(async_client, [mine.id])

    response = await async_client.patch(f"/api/v1/queue/{item.id}", headers=member, json={"printer_id": theirs.id})

    assert response.status_code == 404, response.text
    await db_session.refresh(item)
    assert item.printer_id == mine.id


async def test_the_todo_list_names_no_printer_outside_the_scope(
    async_client: AsyncClient, db_session, two_printers, archive_factory
):
    mine, theirs = two_printers
    await _queue_item(db_session, archive_factory, mine.id, position=1)
    await _queue_item(db_session, archive_factory, theirs.id, position=2)
    admin = _auth(await _admin_token(async_client))
    member = await _member(async_client, [mine.id])
    # Both jobs wait for a staged start, so each printer has an entry.
    for item in (await db_session.execute(select(PrintQueueItem))).scalars().all():
        item.manual_start = True
    await db_session.commit()

    seen = await async_client.get("/api/v1/queue/todo", headers=member)
    everything = await async_client.get("/api/v1/queue/todo", headers=admin)

    assert seen.status_code == 200, seen.text
    assert {g["printer_id"] for g in everything.json()["groups"]} == {mine.id, theirs.id}
    assert {g["printer_id"] for g in seen.json()["groups"]} == {mine.id}
    assert "Theirs" not in seen.text
