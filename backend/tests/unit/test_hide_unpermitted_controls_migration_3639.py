"""Migration coverage for the group option that hides unusable controls (#3639)."""

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.app.core.database import run_migrations
from backend.app.models.group import Group


@pytest.mark.asyncio
async def test_hide_unpermitted_controls_migration_is_additive_and_idempotent(test_engine):
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with session_factory() as db:
        db.add(Group(name="Legacy helpers", permissions=[]))
        await db.commit()

    async with test_engine.begin() as conn:
        await conn.execute(text("ALTER TABLE groups DROP COLUMN hide_unpermitted_controls"))
        await run_migrations(conn)
        await run_migrations(conn)
        columns = await conn.run_sync(
            lambda sync_conn: {col["name"] for col in inspect(sync_conn).get_columns("groups")}
        )
        stored = (
            await conn.execute(text("SELECT hide_unpermitted_controls FROM groups WHERE name = 'Legacy helpers'"))
        ).scalar_one()

    assert "hide_unpermitted_controls" in columns
    assert not stored
