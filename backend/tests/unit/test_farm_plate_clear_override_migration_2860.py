"""farm only: printers.plate_clear_override -> printers.require_plate_clear (#2860).

The farm fork ran a draft of #2860 (PR #3540) that kept the per-printer value
in ``plate_clear_override`` ('inherit' / 'on' / 'off'). Upstream shipped
``require_plate_clear`` (BOOLEAN, NULL follows the app setting). The migration
copies the old values once, so no printer loses its setting on the update:

- 'on' -> TRUE, 'off' -> FALSE, 'inherit' and anything else -> stays NULL
- once only: a value set back to NULL afterwards is not overwritten again
- a value already in require_plate_clear is kept
- the old column and its values stay (rollback to the previous image)
- a database without the old column is left alone
- a new printer can still be inserted although the model no longer maps the
  old NOT NULL column: its database default fills it
"""

from __future__ import annotations

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.core.database import load_all_models, run_migrations
from backend.app.models.printer import Printer
from backend.app.services import plate_clear

FLAG = "_migrate_farm_plate_clear_override_done"

# The statement the draft's migration ran on every farm database (595d81fbc).
DRAFT_ADD_COLUMN = "ALTER TABLE printers ADD COLUMN plate_clear_override VARCHAR(10) NOT NULL DEFAULT 'inherit'"

OLD_VALUES = {1: "on", 2: "off", 3: "inherit", 4: "maybe"}
EXPECTED = {1: True, 2: False, 3: None, 4: None}


@pytest.fixture(autouse=True)
def force_sqlite_dialect(monkeypatch):
    """settings.database_url may point at Postgres in dev configs; the test engine
    is SQLite, so force the dialect both places run_migrations reads it from."""
    from backend.app.core import database as database_module, db_dialect

    monkeypatch.setattr(db_dialect, "is_sqlite", lambda: True)
    monkeypatch.setattr(db_dialect, "is_postgres", lambda: False)
    monkeypatch.setattr(database_module, "is_sqlite", lambda: True)


async def _insert_printer(conn, printer_id: int) -> None:
    await conn.execute(
        load_all_models()
        .tables["printers"]
        .insert()
        .values(
            id=printer_id,
            name=f"Printer {printer_id}",
            serial_number=f"SERIAL{printer_id}",
            ip_address=f"192.168.1.{printer_id}",
            access_code="12345678",
        )
    )


@pytest.fixture
async def draft_engine():
    """A farm database as the draft left it: the old column, no require_plate_clear."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(load_all_models().create_all)
        await conn.execute(text("ALTER TABLE printers DROP COLUMN require_plate_clear"))
        await conn.execute(text(DRAFT_ADD_COLUMN))
        for printer_id, old in OLD_VALUES.items():
            await _insert_printer(conn, printer_id)
            await conn.execute(
                text("UPDATE printers SET plate_clear_override = :v WHERE id = :id"), {"v": old, "id": printer_id}
            )
    yield engine
    await engine.dispose()


@pytest.fixture
async def upstream_engine():
    """A database that never had the draft's column: a fresh install or upstream's."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(load_all_models().create_all)
        await _insert_printer(conn, 1)
    yield engine
    await engine.dispose()


async def _new_values(conn) -> dict[int, bool | None]:
    rows = await conn.execute(text("SELECT id, require_plate_clear FROM printers ORDER BY id"))
    return {row[0]: (None if row[1] is None else bool(row[1])) for row in rows}


async def _old_values(conn) -> dict[int, str]:
    rows = await conn.execute(text("SELECT id, plate_clear_override FROM printers ORDER BY id"))
    return {row[0]: row[1] for row in rows}


async def _flag(conn) -> str | None:
    return (await conn.execute(text('SELECT value FROM settings WHERE "key" = :k'), {"k": FLAG})).scalar_one_or_none()


async def _columns(conn) -> set[str]:
    return {row[1] for row in await conn.execute(text("PRAGMA table_info(printers)"))}


async def test_the_draft_database_is_what_the_test_assumes(draft_engine):
    """Sanity check so the assertions below can't pass by accident."""
    async with draft_engine.begin() as conn:
        columns = await _columns(conn)
        assert "plate_clear_override" in columns
        assert "require_plate_clear" not in columns
        assert await _old_values(conn) == OLD_VALUES


async def test_old_values_are_copied(draft_engine):
    async with draft_engine.begin() as conn:
        await run_migrations(conn)

        assert await _new_values(conn) == EXPECTED
        assert await _flag(conn) == "true"


async def test_the_old_column_and_its_values_stay(draft_engine):
    """Additive only: the previous image still finds its values after a rollback."""
    async with draft_engine.begin() as conn:
        await run_migrations(conn)

        assert await _old_values(conn) == OLD_VALUES


async def test_a_second_run_changes_nothing(draft_engine):
    async with draft_engine.begin() as conn:
        await run_migrations(conn)
        await run_migrations(conn)

        assert await _new_values(conn) == EXPECTED
        assert await _old_values(conn) == OLD_VALUES


async def test_a_value_set_back_to_null_is_not_copied_again(draft_engine):
    """ "Use the setting" chosen in the UI after the update must survive the next start."""
    async with draft_engine.begin() as conn:
        await run_migrations(conn)
        await conn.execute(text("UPDATE printers SET require_plate_clear = NULL WHERE id IN (1, 2)"))
        # ...and one switched the other way round.
        await conn.execute(text("UPDATE printers SET require_plate_clear = TRUE WHERE id = 3"))

        await run_migrations(conn)

        assert await _new_values(conn) == {1: None, 2: None, 3: True, 4: None}
        assert await _old_values(conn) == OLD_VALUES


async def test_a_value_already_set_is_kept(draft_engine):
    """A require_plate_clear that is not NULL wins over the old column."""
    async with draft_engine.begin() as conn:
        await conn.execute(text("ALTER TABLE printers ADD COLUMN require_plate_clear BOOLEAN"))
        await conn.execute(text("UPDATE printers SET require_plate_clear = FALSE WHERE id = 1"))  # old: 'on'
        await conn.execute(text("UPDATE printers SET require_plate_clear = TRUE WHERE id = 2"))  # old: 'off'
        await conn.execute(text("UPDATE printers SET require_plate_clear = TRUE WHERE id = 3"))  # old: 'inherit'

        await run_migrations(conn)

        assert await _new_values(conn) == {1: False, 2: True, 3: True, 4: None}


async def test_values_are_matched_whatever_their_case_or_padding(draft_engine):
    async with draft_engine.begin() as conn:
        await conn.execute(text("UPDATE printers SET plate_clear_override = ' ON ' WHERE id = 3"))
        await conn.execute(text("UPDATE printers SET plate_clear_override = 'Off' WHERE id = 4"))

        await run_migrations(conn)

        assert await _new_values(conn) == {1: True, 2: False, 3: True, 4: False}


async def test_the_production_case_two_printers_on_inherit(draft_engine):
    """Both follow the app setting before and after: NULL, nothing to copy."""
    async with draft_engine.begin() as conn:
        await conn.execute(text("DELETE FROM printers WHERE id IN (3, 4)"))
        await conn.execute(text("UPDATE printers SET plate_clear_override = 'inherit'"))

        await run_migrations(conn)

        assert await _new_values(conn) == {1: None, 2: None}
        assert await _flag(conn) == "true"


async def test_a_database_without_the_old_column_is_untouched(upstream_engine):
    async with upstream_engine.begin() as conn:
        await run_migrations(conn)
        await run_migrations(conn)

        assert "plate_clear_override" not in await _columns(conn)
        assert await _new_values(conn) == {1: None}
        assert await _flag(conn) is None


async def test_the_old_column_fills_itself_on_a_new_printer(draft_engine):
    """The model no longer maps plate_clear_override, which is NOT NULL: its
    database default must cover the insert the app makes for a new printer."""
    async with draft_engine.begin() as conn:
        await run_migrations(conn)
        info = {row[1]: row for row in await conn.execute(text("PRAGMA table_info(printers)"))}
        assert info["plate_clear_override"][3] == 1, "the old column is NOT NULL"
        assert str(info["plate_clear_override"][4]).strip("'") == "inherit", "and has a database default"

    assert "plate_clear_override" not in Printer.__table__.c

    maker = async_sessionmaker(draft_engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        session.add(Printer(name="New", serial_number="SERIALNEW", ip_address="192.168.1.99", access_code="12345678"))
        await session.commit()
        new = (await session.execute(select(Printer).where(Printer.serial_number == "SERIALNEW"))).scalar_one()
        assert new.require_plate_clear is None
        old = await session.scalar(text("SELECT plate_clear_override FROM printers WHERE id = :id"), {"id": new.id})
        assert old == "inherit"

        # The other rows still load, update and delete through the model.
        first = await session.get(Printer, 1)
        first.require_plate_clear = None
        await session.commit()
        await session.delete(await session.get(Printer, 4))
        await session.commit()


async def test_the_cache_sees_the_migrated_values(draft_engine):
    """Startup runs the migrations (init_db) before the plate_clear cache is loaded."""
    from unittest.mock import patch

    from backend.app.services.printer_manager import printer_manager

    async with draft_engine.begin() as conn:
        await run_migrations(conn)

    maker = async_sessionmaker(draft_engine, class_=AsyncSession, expire_on_commit=False)
    awaiting = set(printer_manager._awaiting_plate_clear)
    try:
        with patch("backend.app.core.database.async_session", maker):
            await printer_manager.load_awaiting_plate_clear_from_db()

        assert plate_clear.override(1) is True
        assert plate_clear.override(2) is False
        assert plate_clear.override(3) is None
        # 'on' holds whatever the app setting says, 'off' never, 'inherit' follows it.
        assert [plate_clear.applies(pid, False) for pid in (1, 2, 3)] == [True, False, False]
        assert [plate_clear.applies(pid, True) for pid in (1, 2, 3)] == [True, False, True]
    finally:
        plate_clear.load_overrides({})
        printer_manager._awaiting_plate_clear = awaiting
