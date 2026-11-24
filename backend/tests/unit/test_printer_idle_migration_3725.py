"""Migration test for #3725 -- notification_providers.on_printer_idle_for_filament.

Every existing channel starts with the new event on, as a fresh install does.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from backend.app.core.database import _PG_COLUMNS_SET_FROM_MODEL, load_all_models, run_migrations

COLUMN = "on_printer_idle_for_filament"


@pytest.fixture(autouse=True)
def force_sqlite_dialect(monkeypatch):
    from backend.app.core import database as database_module, db_dialect

    monkeypatch.setattr(db_dialect, "is_sqlite", lambda: True)
    monkeypatch.setattr(db_dialect, "is_postgres", lambda: False)
    monkeypatch.setattr(database_module, "is_sqlite", lambda: True)


@pytest.fixture
async def legacy_engine():
    """A current schema whose providers predate the column, holding one channel."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        metadata = load_all_models()
        await conn.run_sync(metadata.create_all)
        await conn.execute(
            metadata.tables["notification_providers"]
            .insert()
            .values(id=1, name="old", provider_type="ntfy", config="{}")
        )
        await conn.execute(text(f"ALTER TABLE notification_providers DROP COLUMN {COLUMN}"))
    yield engine
    await engine.dispose()


async def test_an_existing_channel_gets_the_event_on(legacy_engine):
    async with legacy_engine.begin() as conn:
        await run_migrations(conn)
        # A second boot must not fail on the column already being there.
        await run_migrations(conn)
        value = (await conn.execute(text(f"SELECT {COLUMN} FROM notification_providers WHERE id = 1"))).scalar_one()
    assert value in (1, True)


async def test_a_null_left_by_create_all_reads_as_on(legacy_engine):
    async with legacy_engine.begin() as conn:
        await conn.execute(text(f"ALTER TABLE notification_providers ADD COLUMN {COLUMN} BOOLEAN"))
        await run_migrations(conn)
        value = (await conn.execute(text(f"SELECT {COLUMN} FROM notification_providers WHERE id = 1"))).scalar_one()
    assert value in (1, True)


def test_postgres_upgrade_gives_the_column_the_models_default():
    assert ("notification_providers", COLUMN) in _PG_COLUMNS_SET_FROM_MODEL
