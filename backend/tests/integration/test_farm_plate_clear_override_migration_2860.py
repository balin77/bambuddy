"""farm only: the app on a database that still has printers.plate_clear_override (#2860).

The one-time copy to require_plate_clear leaves the draft's column in place for
a rollback. The Printer model no longer maps it and it is NOT NULL, so the
printer routes must still be able to create, change and delete a printer: the
column's database default fills it. Runs on the test engine, so on PostgreSQL
too where the suite is pointed at one.
"""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from backend.app.core.database import _migrate_farm_plate_clear_override
from backend.app.services import plate_clear

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

# The statement the draft's migration ran on every farm database (595d81fbc).
DRAFT_ADD_COLUMN = "ALTER TABLE printers ADD COLUMN plate_clear_override VARCHAR(10) NOT NULL DEFAULT 'inherit'"


@pytest.fixture(autouse=True)
def _mock_printer_test_connection():
    """POST /printers/ probes the printer before it saves; answer the probe."""
    with patch(
        "backend.app.services.printer_manager.printer_manager.test_connection",
        new=AsyncMock(return_value={"success": True, "state": "IDLE", "model": "A1"}),
    ):
        yield


@pytest.fixture
async def draft_database(test_engine, printer_factory):
    """Three printers the draft set to on / off / inherit, then the farm migration."""
    plate_clear.load_overrides({})
    printers = {mode: await printer_factory(name=mode) for mode in ("on", "off", "inherit")}
    ids = {mode: printer.id for mode, printer in printers.items()}
    async with test_engine.begin() as conn:
        await conn.execute(text(DRAFT_ADD_COLUMN))
        for mode, printer_id in ids.items():
            await conn.execute(
                text("UPDATE printers SET plate_clear_override = :v WHERE id = :id"), {"v": mode, "id": printer_id}
            )
        await _migrate_farm_plate_clear_override(conn)
    yield ids
    plate_clear.load_overrides({})
    async with test_engine.begin() as conn:
        await conn.execute(text("ALTER TABLE printers DROP COLUMN plate_clear_override"))
        await conn.execute(text("DELETE FROM settings WHERE \"key\" = '_migrate_farm_plate_clear_override_done'"))


async def test_the_api_reports_the_migrated_values(async_client: AsyncClient, draft_database):
    values = {}
    for mode, printer_id in draft_database.items():
        response = await async_client.get(f"/api/v1/printers/{printer_id}")
        assert response.status_code == 200
        values[mode] = response.json()["require_plate_clear"]

    assert values == {"on": True, "off": False, "inherit": None}


async def test_a_new_printer_can_be_created(async_client: AsyncClient, test_engine, draft_database):
    response = await async_client.post(
        "/api/v1/printers/",
        json={
            "name": "New Printer",
            "serial_number": "00M09A999999999",
            "ip_address": "192.168.1.250",
            "access_code": "12345678",
            "model": "A1",
        },
    )

    assert response.status_code == 200, response.text
    created = response.json()
    assert created["require_plate_clear"] is None
    async with test_engine.begin() as conn:
        old = (
            await conn.execute(text("SELECT plate_clear_override FROM printers WHERE id = :id"), {"id": created["id"]})
        ).scalar_one()
    assert old == "inherit"


async def test_use_the_setting_survives_the_next_start(async_client: AsyncClient, test_engine, draft_database):
    """Back to "Use the setting" in Edit Printer; the next start must not copy 'on' again."""
    printer_id = draft_database["on"]

    response = await async_client.patch(f"/api/v1/printers/{printer_id}", json={"require_plate_clear": None})
    assert response.status_code == 200
    assert response.json()["require_plate_clear"] is None

    async with test_engine.begin() as conn:
        await _migrate_farm_plate_clear_override(conn)
        old = (
            await conn.execute(text("SELECT plate_clear_override FROM printers WHERE id = :id"), {"id": printer_id})
        ).scalar_one()

    response = await async_client.get(f"/api/v1/printers/{printer_id}")
    assert response.json()["require_plate_clear"] is None
    assert old == "on", "the old column keeps its value for a rollback"


async def test_a_printer_can_be_changed_and_deleted(async_client: AsyncClient, draft_database):
    printer_id = draft_database["inherit"]

    response = await async_client.patch(f"/api/v1/printers/{printer_id}", json={"require_plate_clear": False})
    assert response.status_code == 200
    assert response.json()["require_plate_clear"] is False

    response = await async_client.delete(f"/api/v1/printers/{printer_id}")
    assert response.status_code in (200, 204)
