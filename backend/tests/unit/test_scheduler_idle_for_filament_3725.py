"""A printer idle for five minutes with only filament-blocked jobs is reported (#3725).

Driven through ``check_queue`` with a clock the test moves. Each pass collects which
printers were idle where a job was held back for filament; the watch keeps the clock
per printer, in the settings table, so a restart neither starts it over nor repeats it.
"""

import json
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import backend.app.models  # noqa: F401 - populate Base.metadata
from backend.app.core.database import Base
from backend.app.models.library import LibraryFile
from backend.app.models.print_queue import PrintQueueItem
from backend.app.models.printer import Printer
from backend.app.models.settings import Settings
from backend.app.models.smart_plug import SmartPlug
from backend.app.services.filament_deficit import FilamentDeficit
from backend.app.services.filament_idle_watch import SETTING_KEY
from backend.app.services.print_scheduler import PrintScheduler
from backend.app.services.queue_todo import todo_filament_from_requirement

# The idle clock is patched, but the maximum wait and a scheduled start read the
# real clock: T0 has to be "now", or the jobs gain priority once 60 hours pass.
T0 = datetime.now(timezone.utc).replace(microsecond=0)
DEFICIT = [
    FilamentDeficit(slot_id=1, ams_id=0, tray_id=2, filament_type="PLA", required_grams=505.0, remaining_grams=196.0)
]
PETG = [
    FilamentDeficit(slot_id=2, ams_id=0, tray_id=1, filament_type="PETG", required_grams=90.0, remaining_grams=10.0)
]
BROWN = [{"slot_id": 1, "type": "PLA", "color": "#7D6556", "color_name": "Army Beige"}]


@pytest.fixture
async def ctx():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    async with session_maker() as db:
        db.add_all(
            [
                Printer(
                    id=pid,
                    name=name,
                    serial_number=f"SN000{pid}",
                    ip_address=f"10.0.0.{pid}",
                    access_code="x",
                    model=model,
                    is_active=True,
                )
                for pid, name, model in ((1, "P1S right", "P1S"), (2, "P1S left", "P1S"), (3, "X1C one", "X1C"))
            ]
        )
        db.add_all(
            [
                Settings(key="queue_loaded_filament_first", value="true"),
                Settings(key="queue_max_wait_hours", value="60"),
            ]
        )
        await db.commit()
    try:
        yield SimpleNamespace(session_maker=session_maker, now=[T0])
    finally:
        await engine.dispose()


def new_scheduler(ctx):
    scheduler = PrintScheduler()
    scheduler._idle_watch.clock = lambda: ctx.now[0]
    return scheduler


async def add_item(ctx, name="Lamp", **fields):
    async with ctx.session_maker() as db:
        lib = LibraryFile(
            filename=f"{name}.3mf", file_path=f"/library/{name}.3mf", file_size=10, file_type="3mf", file_metadata={}
        )
        db.add(lib)
        await db.flush()
        item = PrintQueueItem(
            status="pending",
            position=fields.pop("position", 1),
            library_file_id=lib.id,
            created_at=T0.replace(tzinfo=None),
            **fields,
        )
        db.add(item)
        await db.commit()
        return item.id


async def one_pass(
    ctx,
    scheduler,
    *,
    deficits=None,
    unmatched=None,
    short=frozenset(),
    short_facts=None,
    unmatched_on=frozenset(),
    idle=lambda pid: True,
    connected=lambda pid: True,
    state="IDLE",
    interlocked=None,
    idle_event=None,
    waiting=None,
    extra=(),
    trays=None,
    plate_clear=frozenset(),
):
    """One check_queue pass; ``deficits``/``unmatched``: item id -> what the pinned gate finds."""
    idle_event = idle_event if idle_event is not None else AsyncMock()
    waiting = waiting if waiting is not None else AsyncMock()
    deficits = deficits or {}
    unmatched = unmatched or {}

    async def deficit(db, item, *, printer_id=None, ams_mapping=None, require_known=False):
        return deficits.get(item.id, [])

    async def unmatched_requirements(db, item, printer_id, mapping):
        return list(unmatched.get(item.id, []))

    async def short_on(db, item, printer_id, *, require_known=False):
        return printer_id in short

    async def short_filaments_on(db, item, printer_id):
        if printer_id in short:
            return await real_deficit_todo(db, item, list(short_facts or DEFICIT))
        return []

    async def unmatched_on_check(db, item, printer_id):
        if printer_id in unmatched_on:
            scheduler._unmatched_todo_memo[scheduler._unmatched_key(item, printer_id)] = [
                todo_filament_from_requirement(r) for r in BROWN
            ]
            return ["PLA Army Beige"]
        return []

    real_deficit_todo = scheduler._deficit_todo_filaments
    launched = MagicMock()
    status = SimpleNamespace(raw_data={}, state=state)
    trays = trays or {}
    patches = [
        patch("backend.app.services.print_scheduler.async_session", ctx.session_maker),
        patch("backend.app.core.database.async_session", ctx.session_maker),
        patch("backend.app.services.print_scheduler.printer_manager.is_connected", MagicMock(side_effect=connected)),
        patch("backend.app.services.print_scheduler.printer_manager.get_status", MagicMock(return_value=status)),
        patch(
            "backend.app.services.print_scheduler.printer_manager.is_awaiting_plate_clear",
            MagicMock(side_effect=lambda pid: pid in plate_clear),
        ),
        patch(
            "backend.app.services.print_scheduler.printer_manager.last_known_trays",
            MagicMock(side_effect=lambda pid: trays.get(pid, {})),
        ),
        patch(
            "backend.app.services.print_scheduler.ha_sensor_manager.blocked_printers",
            AsyncMock(return_value=interlocked or {}),
        ),
        patch("backend.app.services.notification_service.notification_service.on_queue_job_waiting", waiting),
        patch("backend.app.services.notification_service.notification_service.on_queue_job_assigned", AsyncMock()),
        patch("backend.app.services.notification_service.notification_service.on_queue_job_failed", AsyncMock()),
        patch(
            "backend.app.services.notification_service.notification_service.on_printer_idle_for_filament", idle_event
        ),
        patch("backend.app.services.print_batch.refresh_batches_after", AsyncMock()),
        patch("backend.app.services.print_scheduler.compute_deficit_for_queue_item", AsyncMock(side_effect=deficit)),
        patch.object(scheduler, "_unmatched_on", AsyncMock(side_effect=unmatched_on_check)),
        patch.object(scheduler, "_unmatched_requirements", AsyncMock(side_effect=unmatched_requirements)),
        patch.object(scheduler, "_filament_short_on", AsyncMock(side_effect=short_on)),
        patch.object(scheduler, "_short_filaments_on", AsyncMock(side_effect=short_filaments_on)),
        patch.object(scheduler, "_is_printer_idle", MagicMock(side_effect=lambda pid, *a, **k: idle(pid))),
        patch.object(scheduler, "_check_auto_drying", AsyncMock()),
        patch.object(scheduler, "_ensure_ams_mapping", AsyncMock(return_value=None)),
        patch.object(scheduler, "_launch_uploads", launched),
    ]
    with ExitStack() as stack:
        for p in [*patches, *extra]:
            stack.enter_context(p)
        await scheduler.check_queue()
    return SimpleNamespace(event=idle_event, launched=launched, waiting=waiting)


async def saved_raw(ctx) -> dict:
    async with ctx.session_maker() as db:
        raw = await db.scalar(select(Settings.value).where(Settings.key == SETTING_KEY))
    return json.loads(raw) if raw else {}


async def saved(ctx) -> dict:
    """The saved clocks of the printers, without the short spools told about."""
    return {k: v for k, v in (await saved_raw(ctx)).items() if k != "short"}


def at(ctx, seconds):
    ctx.now[0] = T0 + timedelta(seconds=seconds)


class TestFiresAfterFiveMinutes:
    @pytest.mark.asyncio
    async def test_not_before_300_seconds_then_once(self, ctx):
        scheduler = new_scheduler(ctx)
        item = await add_item(ctx, "Lamp_Base", printer_id=1)

        first = await one_pass(ctx, scheduler, deficits={item: DEFICIT})
        at(ctx, 299)
        early = await one_pass(ctx, scheduler, deficits={item: DEFICIT})
        at(ctx, 300)
        due = await one_pass(ctx, scheduler, deficits={item: DEFICIT})
        at(ctx, 900)
        again = await one_pass(ctx, scheduler, deficits={item: DEFICIT})

        first.event.assert_not_awaited()
        early.event.assert_not_awaited()
        due.event.assert_awaited_once()
        again.event.assert_not_awaited()
        printer_id, printer_name, jobs, _db = due.event.await_args.args
        assert (printer_id, printer_name) == (1, "P1S right")
        assert [j.name for j in jobs] == ["Lamp_Base"]
        (need,) = jobs[0].needs
        assert (need.filament.type, need.filament.slot, need.have_grams, need.need_grams) == ("PLA", "A3", 196.0, 505.0)

    @pytest.mark.asyncio
    async def test_unmatched_filament_is_a_filament_to_load(self, ctx):
        scheduler = new_scheduler(ctx)
        item = await add_item(ctx, "Coaster", printer_id=1)
        await one_pass(ctx, scheduler, unmatched={item: BROWN})
        at(ctx, 300)

        due = await one_pass(ctx, scheduler, unmatched={item: BROWN})

        (need,) = due.event.await_args.args[2][0].needs
        assert (need.filament.type, need.filament.color_name, need.need_grams) == ("PLA", "Army Beige", None)

    @pytest.mark.asyncio
    async def test_two_jobs_are_one_message(self, ctx):
        scheduler = new_scheduler(ctx)
        a = await add_item(ctx, "Lamp", printer_id=1, position=1)
        b = await add_item(ctx, "Coaster", printer_id=1, position=2)
        blocked = {a: DEFICIT, b: DEFICIT}
        await one_pass(ctx, scheduler, deficits=blocked)
        at(ctx, 300)

        due = await one_pass(ctx, scheduler, deficits=blocked)

        due.event.assert_awaited_once()
        assert [j.name for j in due.event.await_args.args[2]] == ["Lamp", "Coaster"]


class TestStagedJobs:
    @pytest.mark.asyncio
    async def test_a_job_staged_for_a_short_spool_counts(self, ctx):
        """Staged for a short spool, its printer stands idle all the same."""
        scheduler = new_scheduler(ctx)
        item = await add_item(ctx, "Lamp", printer_id=1, manual_start=True, filament_short=True)
        await one_pass(ctx, scheduler, deficits={item: DEFICIT})
        at(ctx, 300)

        due = await one_pass(ctx, scheduler, deficits={item: DEFICIT})

        due.event.assert_awaited_once()
        assert [j.name for j in due.event.await_args.args[2]] == ["Lamp"]

    @pytest.mark.asyncio
    async def test_a_staged_job_whose_spool_was_refilled_does_not(self, ctx):
        scheduler = new_scheduler(ctx)
        item = await add_item(ctx, printer_id=1, manual_start=True, filament_short=True)
        await one_pass(ctx, scheduler, deficits={item: []})
        at(ctx, 300)

        due = await one_pass(ctx, scheduler, deficits={item: []})

        due.event.assert_not_awaited()


class TestAgainOnlyWhenSomethingChanged:
    @pytest.mark.asyncio
    async def test_after_a_print_in_between(self, ctx):
        scheduler = new_scheduler(ctx)
        item = await add_item(ctx, printer_id=1)
        blocked = {item: DEFICIT}
        await one_pass(ctx, scheduler, deficits=blocked)
        at(ctx, 300)
        assert (await one_pass(ctx, scheduler, deficits=blocked)).event.await_count == 1

        at(ctx, 400)
        await one_pass(ctx, scheduler, deficits=blocked, idle=lambda pid: False, state="RUNNING")
        at(ctx, 500)
        await one_pass(ctx, scheduler, deficits=blocked)
        at(ctx, 799)
        early = await one_pass(ctx, scheduler, deficits=blocked)
        at(ctx, 800)
        again = await one_pass(ctx, scheduler, deficits=blocked)

        early.event.assert_not_awaited()
        again.event.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_when_the_filaments_change(self, ctx):
        scheduler = new_scheduler(ctx)
        item = await add_item(ctx, printer_id=1)
        await one_pass(ctx, scheduler, deficits={item: DEFICIT})
        at(ctx, 300)
        await one_pass(ctx, scheduler, deficits={item: DEFICIT})

        at(ctx, 360)
        same_filament_fewer_grams = await one_pass(
            ctx,
            scheduler,
            deficits={item: [FilamentDeficit(1, 0, 2, "PLA", 505.0, 150.0)]},
        )
        at(ctx, 420)
        # The new short spool is told about first, the printer the pass after.
        await one_pass(ctx, scheduler, deficits={item: PETG})
        at(ctx, 430)
        other = await one_pass(ctx, scheduler, deficits={item: PETG})

        same_filament_fewer_grams.event.assert_not_awaited()
        other.event.assert_awaited_once()


class TestNotIdleForFilament:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "kind",
        ["plate_clear_or_printing", "interlock", "drying", "no_job", "scheduled", "print_anyway", "staged_other"],
    )
    async def test_other_reasons_never_fire(self, ctx, kind):
        scheduler = new_scheduler(ctx)
        fields = {"printer_id": 1}
        idle = lambda pid: True  # noqa: E731
        interlocked = None
        if kind == "scheduled":
            fields["scheduled_time"] = (T0 + timedelta(days=2)).replace(tzinfo=None)
        if kind == "print_anyway":
            fields["skip_filament_check"] = True
        if kind == "staged_other":
            fields["manual_start"] = True
        if kind == "plate_clear_or_printing":
            idle = lambda pid: False  # noqa: E731
        if kind == "interlock":
            interlocked = {1: "Enclosure Door"}
        if kind == "drying":
            scheduler._drying_in_progress[1] = object()
            await _set_setting(ctx, "queue_drying_block", "true")
        item = await add_item(ctx, **fields) if kind != "no_job" else None
        blocked = {item: DEFICIT} if item else {}

        results = []
        for seconds in (0, 300, 600):
            at(ctx, seconds)
            results.append(await one_pass(ctx, scheduler, deficits=blocked, idle=idle, interlocked=interlocked))

        assert all(r.event.await_count == 0 for r in results)
        assert await saved(ctx) == {}

    @pytest.mark.asyncio
    async def test_a_printer_that_gets_another_job_is_not_idle(self, ctx):
        scheduler = new_scheduler(ctx)
        blocked_job = await add_item(ctx, "Blocked", printer_id=1, position=1)
        await add_item(ctx, "Fine", printer_id=1, position=2)

        first = await one_pass(ctx, scheduler, deficits={blocked_job: DEFICIT})
        at(ctx, 300)
        second = await one_pass(ctx, scheduler, deficits={blocked_job: DEFICIT})

        assert first.launched.called
        second.event.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_an_emptied_queue_forgets_the_clock(self, ctx):
        scheduler = new_scheduler(ctx)
        item = await add_item(ctx, printer_id=1)
        await one_pass(ctx, scheduler, deficits={item: DEFICIT})
        assert list(await saved(ctx)) == ["1"]

        async with ctx.session_maker() as db:
            row = await db.get(PrintQueueItem, item)
            row.status = "cancelled"
            await db.commit()
        at(ctx, 200)
        await one_pass(ctx, scheduler)
        at(ctx, 300)
        await add_item(ctx, "New", printer_id=1)  # a new job: the five minutes start afresh
        again = await one_pass(ctx, scheduler, deficits={item + 1: DEFICIT})

        again.event.assert_not_awaited()
        assert await saved(ctx) == {"1": {"since": ctx.now[0].isoformat(), "announced": None}}


class TestFrozenAndShrinking:
    @pytest.mark.asyncio
    async def test_an_interlock_between_two_passes_does_not_repeat_the_message(self, ctx):
        scheduler = new_scheduler(ctx)
        item = await add_item(ctx, printer_id=1)
        blocked = {item: DEFICIT}
        await one_pass(ctx, scheduler, deficits=blocked)
        at(ctx, 300)
        assert (await one_pass(ctx, scheduler, deficits=blocked)).event.await_count == 1

        at(ctx, 400)
        await one_pass(ctx, scheduler, deficits=blocked, interlocked={1: "Enclosure Door"})
        at(ctx, 1000)
        after = await one_pass(ctx, scheduler, deficits=blocked)

        after.event.assert_not_awaited()
        assert (await saved(ctx))["1"]["announced"] is not None

    @pytest.mark.asyncio
    async def test_fewer_filaments_are_remembered_without_a_message(self, ctx):
        scheduler = new_scheduler(ctx)
        a = await add_item(ctx, "A", printer_id=1, position=1)
        b = await add_item(ctx, "B", printer_id=1, position=2)
        await one_pass(ctx, scheduler, deficits={a: DEFICIT, b: PETG})
        at(ctx, 300)
        assert (await one_pass(ctx, scheduler, deficits={a: DEFICIT, b: PETG})).event.await_count == 1

        async with ctx.session_maker() as db:
            (await db.get(PrintQueueItem, b)).status = "cancelled"
            await db.commit()
        at(ctx, 400)
        shrunk = await one_pass(ctx, scheduler, deficits={a: DEFICIT})
        at(ctx, 500)
        same = await one_pass(ctx, scheduler, deficits={a: DEFICIT})
        c = await add_item(ctx, "C", printer_id=1, position=3)
        at(ctx, 600)
        await one_pass(ctx, scheduler, deficits={a: DEFICIT, c: PETG})  # the short spool is told first
        at(ctx, 610)
        back = await one_pass(ctx, scheduler, deficits={a: DEFICIT, c: PETG})

        shrunk.event.assert_not_awaited()
        same.event.assert_not_awaited()
        back.event.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_a_printer_seen_again_after_being_off_starts_its_five_minutes_over(self, ctx):
        scheduler = new_scheduler(ctx)
        item = await add_item(ctx, printer_id=1)
        blocked = {item: DEFICIT}
        await one_pass(ctx, scheduler, deficits=blocked)
        at(ctx, 200)
        await one_pass(
            ctx, scheduler, deficits=blocked, idle=lambda pid: False, connected=lambda pid: False, state="unknown"
        )
        at(ctx, 400)
        back = await one_pass(ctx, scheduler, deficits=blocked)
        at(ctx, 600)
        early = await one_pass(ctx, scheduler, deficits=blocked)
        at(ctx, 700)
        due = await one_pass(ctx, scheduler, deficits=blocked)

        back.event.assert_not_awaited()
        early.event.assert_not_awaited()
        due.event.assert_awaited_once()


class TestModelJobs:
    @pytest.mark.asyncio
    async def test_only_idle_printers_count(self, ctx):
        scheduler = new_scheduler(ctx)
        await add_item(ctx, "Lamp", target_model="P1S")
        # Both P1S lack the filament; one is printing: only the idle one stands.
        only_idle = lambda pid: pid != 2  # noqa: E731
        await one_pass(ctx, scheduler, unmatched_on={1, 2}, idle=only_idle)
        at(ctx, 300)

        due = await one_pass(ctx, scheduler, unmatched_on={1, 2}, idle=only_idle)

        due.event.assert_awaited_once()
        assert due.event.await_args.args[:2] == (1, "P1S right")
        assert list(await saved(ctx)) == ["1"]

    @pytest.mark.asyncio
    async def test_a_short_spool_names_the_amounts(self, ctx):
        scheduler = new_scheduler(ctx)
        await add_item(ctx, "Lamp", target_model="P1S")
        await one_pass(ctx, scheduler, short={1, 2})
        at(ctx, 300)

        due = await one_pass(ctx, scheduler, short={1, 2})

        assert due.event.await_count == 2
        (need,) = due.event.await_args_list[0].args[2][0].needs
        assert (need.have_grams, need.need_grams) == (196.0, 505.0)

    @pytest.mark.asyncio
    async def test_a_job_that_starts_elsewhere_does_not_hold_the_other_printer(self, ctx):
        scheduler = new_scheduler(ctx)
        await add_item(ctx, "Lamp", target_model="P1S")
        await one_pass(ctx, scheduler, unmatched_on={1})
        at(ctx, 300)

        due = await one_pass(ctx, scheduler, unmatched_on={1})

        due.event.assert_not_awaited()
        assert await saved(ctx) == {}


class TestRestart:
    @pytest.mark.asyncio
    async def test_an_announced_standstill_is_not_repeated(self, ctx):
        item = await add_item(ctx, printer_id=1)
        first = new_scheduler(ctx)
        await one_pass(ctx, first, deficits={item: DEFICIT})
        at(ctx, 300)
        assert (await one_pass(ctx, first, deficits={item: DEFICIT})).event.await_count == 1

        at(ctx, 360)
        restarted = new_scheduler(ctx)
        again = await one_pass(ctx, restarted, deficits={item: DEFICIT})
        at(ctx, 900)
        later = await one_pass(ctx, restarted, deficits={item: DEFICIT})

        again.event.assert_not_awaited()
        later.event.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_the_five_minutes_continue_across_a_restart(self, ctx):
        item = await add_item(ctx, printer_id=1)
        await one_pass(ctx, new_scheduler(ctx), deficits={item: DEFICIT})
        at(ctx, 301)

        due = await one_pass(ctx, new_scheduler(ctx), deficits={item: DEFICIT})

        due.event.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_a_stored_start_older_than_five_minutes_fires_at_the_first_pass(self, ctx):
        item = await add_item(ctx, printer_id=1)
        await _set_setting(
            ctx,
            SETTING_KEY,
            json.dumps({"1": {"since": (T0 - timedelta(hours=2)).isoformat(), "announced": None}}),
        )

        scheduler = new_scheduler(ctx)
        # The pass that finds the short spool tells about it; the printer follows in the next.
        await one_pass(ctx, scheduler, deficits={item: DEFICIT})
        due = await one_pass(ctx, scheduler, deficits={item: DEFICIT})

        due.event.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_seen_printing_removes_the_entry(self, ctx):
        item = await add_item(ctx, printer_id=1)
        scheduler = new_scheduler(ctx)
        await one_pass(ctx, scheduler, deficits={item: DEFICIT})
        assert "1" in await saved(ctx)

        await one_pass(ctx, scheduler, deficits={item: DEFICIT}, idle=lambda pid: False, state="RUNNING")

        assert await saved(ctx) == {}

    @pytest.mark.asyncio
    async def test_a_printer_that_has_not_reported_yet_keeps_its_clock(self, ctx):
        item = await add_item(ctx, printer_id=1)
        scheduler = new_scheduler(ctx)
        await one_pass(ctx, scheduler, deficits={item: DEFICIT})
        before = await saved(ctx)

        await one_pass(
            ctx,
            scheduler,
            deficits={item: DEFICIT},
            idle=lambda pid: False,
            connected=lambda pid: False,
            state="unknown",
        )

        assert await saved(ctx) == before

    @pytest.mark.asyncio
    async def test_unreadable_state_is_ignored(self, ctx):
        item = await add_item(ctx, printer_id=1)
        await _set_setting(ctx, SETTING_KEY, "{not json")
        scheduler = new_scheduler(ctx)

        await one_pass(ctx, scheduler, deficits={item: DEFICIT})
        at(ctx, 300)
        due = await one_pass(ctx, scheduler, deficits={item: DEFICIT})

        due.event.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_the_entry_of_a_deleted_printer_is_dropped(self, ctx):
        await add_item(ctx, printer_id=1)
        await _set_setting(ctx, SETTING_KEY, json.dumps({"99": {"since": T0.isoformat(), "announced": None}}))

        await one_pass(ctx, new_scheduler(ctx))

        assert await saved(ctx) == {}

    @pytest.mark.asyncio
    async def test_it_is_written_when_it_changes_not_every_pass(self, ctx):
        item = await add_item(ctx, printer_id=1)
        scheduler = new_scheduler(ctx)
        writes = AsyncMock()
        from backend.app.core import db_dialect

        real = db_dialect.upsert_setting

        async def counting(db, model, key, value):
            await writes(key, value)
            await real(db, model, key, value)

        with patch("backend.app.services.filament_idle_watch.upsert_setting", counting):
            for seconds in (0, 10, 20, 30):
                at(ctx, seconds)
                await one_pass(ctx, scheduler, deficits={item: DEFICIT})
            at(ctx, 300)
            await one_pass(ctx, scheduler, deficits={item: DEFICIT})
            for seconds in (310, 320, 330):
                at(ctx, seconds)
                await one_pass(ctx, scheduler, deficits={item: DEFICIT})

        # The start, then the announcement.
        assert writes.await_count == 2


PLA_TRAYS = {"ams": [{"tray": [{"tray_type": "PLA", "tray_color": "FFFFFFFF"}]}]}
PETG_TRAYS = {"ams": [{"tray": [{"tray_type": "PETG", "tray_color": "FFFFFFFF"}]}]}
PETG_ONLY = json.dumps(["PETG"])
PLA_ONLY = json.dumps(["PLA"])


async def add_plug(ctx, printer_id, *, last_state="OFF", plug_type="tasmota", auto_on=True):
    async with ctx.session_maker() as db:
        db.add(
            SmartPlug(
                name=f"plug {printer_id}",
                ip_address="10.1.0.1",
                plug_type=plug_type,
                printer_id=printer_id,
                auto_on=auto_on,
                last_state=last_state,
            )
        )
        await db.commit()


def off(*printers):
    """The printers in ``printers`` are switched off: not connected, so not idle."""
    return {
        "connected": lambda pid: pid not in printers,
        "idle": lambda pid: pid not in printers,
    }


async def pass_pair(ctx, scheduler, **kw):
    """The first pass and the one five minutes later; returns the second."""
    await one_pass(ctx, scheduler, **kw)
    at(ctx, 300)
    return await one_pass(ctx, scheduler, **kw)


def announced_printers(result):
    return sorted(call.args[0] for call in result.event.await_args_list)


class TestSwitchedOffPrinters:
    """A printer its smart plug switched off waits for filament like an idle one (#3725)."""

    @pytest.mark.asyncio
    async def test_pinned_job_on_a_plug_off_printer_fires_after_five_minutes(self, ctx):
        await add_plug(ctx, 1)
        scheduler = new_scheduler(ctx)
        await add_item(ctx, "Lamp", printer_id=1, required_filament_types=PETG_ONLY)
        kw = {**off(1), "trays": {1: PLA_TRAYS}}

        first = await one_pass(ctx, scheduler, **kw)
        at(ctx, 299)
        early = await one_pass(ctx, scheduler, **kw)
        at(ctx, 300)
        due = await one_pass(ctx, scheduler, **kw)
        at(ctx, 900)
        again = await one_pass(ctx, scheduler, **kw)

        first.event.assert_not_awaited()
        early.event.assert_not_awaited()
        due.event.assert_awaited_once()
        again.event.assert_not_awaited()
        printer_id, printer_name, jobs, _db = due.event.await_args.args
        assert (printer_id, printer_name) == (1, "P1S right")
        assert [j.name for j in jobs] == ["Lamp"]
        (need,) = jobs[0].needs
        assert need.filament.type == "PETG"

    @pytest.mark.asyncio
    async def test_model_job_on_a_plug_off_printer_fires_after_five_minutes(self, ctx):
        await add_plug(ctx, 1)
        scheduler = new_scheduler(ctx)
        await add_item(ctx, "Lamp", target_model="P1S", required_filament_types=PETG_ONLY)

        due = await pass_pair(ctx, scheduler, **off(1), trays={1: PLA_TRAYS})

        assert 1 in announced_printers(due)
        call = next(c for c in due.event.await_args_list if c.args[0] == 1)
        (need,) = call.args[2][0].needs
        assert need.filament.type == "PETG"

    @pytest.mark.asyncio
    async def test_once_per_standstill_also_for_a_switched_off_printer(self, ctx):
        await add_plug(ctx, 1)
        scheduler = new_scheduler(ctx)
        await add_item(ctx, "Lamp", printer_id=1, required_filament_types=PETG_ONLY)
        kw = {**off(1), "trays": {1: PLA_TRAYS}}
        await one_pass(ctx, scheduler, **kw)
        at(ctx, 300)
        assert (await one_pass(ctx, scheduler, **kw)).event.await_count == 1

        at(ctx, 1200)
        later = await one_pass(ctx, scheduler, **kw)
        # It was on and printing in between, then off again: a new standstill.
        at(ctx, 1300)
        await one_pass(ctx, scheduler, idle=lambda pid: False, state="RUNNING", trays={1: PLA_TRAYS})
        at(ctx, 1400)
        await one_pass(ctx, scheduler, **kw)
        at(ctx, 1700)
        second = await one_pass(ctx, scheduler, **kw)

        later.event.assert_not_awaited()
        second.event.assert_awaited_once()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("kind", ["pinned", "model"])
    @pytest.mark.parametrize("case", ["plug_on", "no_plug", "auto_on_off", "unknown_trays"])
    async def test_what_does_not_count(self, ctx, kind, case):
        if case == "plug_on":
            await add_plug(ctx, 1, last_state="ON")
        elif case == "auto_on_off":
            await add_plug(ctx, 1, auto_on=False)
        elif case != "no_plug":
            await add_plug(ctx, 1)
        fields = {"printer_id": 1} if kind == "pinned" else {"target_model": "P1S"}
        await add_item(ctx, "Lamp", required_filament_types=PETG_ONLY, **fields)
        trays = {} if case == "unknown_trays" else {1: PLA_TRAYS}

        due = await pass_pair(ctx, new_scheduler(ctx), **off(1), trays=trays)

        assert 1 not in announced_printers(due) if due.event.await_count else True

    @pytest.mark.asyncio
    @pytest.mark.parametrize("kind", ["pinned", "model"])
    async def test_a_job_that_would_switch_it_on_means_it_is_not_waiting(self, ctx, kind):
        await add_plug(ctx, 1)
        scheduler = new_scheduler(ctx)
        if kind == "pinned":
            await add_item(ctx, "Needs PETG", printer_id=1, required_filament_types=PETG_ONLY, position=1)
            await add_item(ctx, "Fits", printer_id=1, required_filament_types=PLA_ONLY, position=2)
        else:
            await add_item(ctx, "Needs PETG", target_model="P1S", required_filament_types=PETG_ONLY, position=1)
            await add_item(ctx, "Fits", target_model="P1S", required_filament_types=PLA_ONLY, position=2)
        extra = (
            patch.object(scheduler, "_power_on_and_wait", AsyncMock(return_value=False)),
            patch.object(scheduler, "_wake_printer_for_model", AsyncMock(return_value=(None, None))),
        )

        due = await pass_pair(ctx, scheduler, **off(1), trays={1: PLA_TRAYS}, extra=extra)

        assert 1 not in announced_printers(due) if due.event.await_count else True

    @pytest.mark.asyncio
    async def test_a_model_job_that_another_off_printer_fits_does_not_hold_the_first(self, ctx):
        """P1S right lacks PETG, P1S left was last loaded with it: the job goes there once it is switched on."""
        await add_plug(ctx, 1)
        await add_plug(ctx, 2)
        scheduler = new_scheduler(ctx)
        await add_item(ctx, "Lamp", target_model="P1S", required_filament_types=PETG_ONLY)
        extra = (patch.object(scheduler, "_wake_printer_for_model", AsyncMock(return_value=(None, None))),)

        due = await pass_pair(ctx, scheduler, **off(1, 2), trays={1: PLA_TRAYS, 2: PETG_TRAYS}, extra=extra)

        due.event.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_plate_to_clear_is_not_waiting_for_filament(self, ctx):
        await add_plug(ctx, 1)
        await _set_setting(ctx, "require_plate_clear", "true")
        await add_item(ctx, "Lamp", printer_id=1, required_filament_types=PETG_ONLY)

        due = await pass_pair(ctx, new_scheduler(ctx), **off(1), trays={1: PLA_TRAYS}, plate_clear={1})

        due.event.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_failed_power_on_cooling_off_is_not_waiting_for_filament(self, ctx):
        await add_plug(ctx, 1)
        scheduler = new_scheduler(ctx)
        await add_item(ctx, "Lamp", printer_id=1, required_filament_types=PETG_ONLY)
        scheduler._wake_failures[1] = float("inf")

        due = await pass_pair(ctx, scheduler, **off(1), trays={1: PLA_TRAYS})

        due.event.assert_not_awaited()


class TestLoadedFilamentFirst:
    """The event exists only with "Loaded filament first" (#3725)."""

    @pytest.mark.asyncio
    async def test_nothing_with_the_setting_off_and_the_clock_starts_when_it_is_turned_on(self, ctx):
        await _set_setting(ctx, "queue_loaded_filament_first", "false")
        scheduler = new_scheduler(ctx)
        item = await add_item(ctx, "Lamp", printer_id=1, manual_start=True, filament_short=True)
        blocked = {item: DEFICIT}

        results = []
        for seconds in (0, 300, 600):
            at(ctx, seconds)
            results.append(await one_pass(ctx, scheduler, deficits=blocked))
        assert all(r.event.await_count == 0 for r in results)
        assert await saved(ctx) == {}

        await _set_setting(ctx, "queue_loaded_filament_first", "true")
        at(ctx, 700)
        started = await one_pass(ctx, scheduler, deficits=blocked)
        at(ctx, 999)
        early = await one_pass(ctx, scheduler, deficits=blocked)
        at(ctx, 1000)
        due = await one_pass(ctx, scheduler, deficits=blocked)

        started.event.assert_not_awaited()
        early.event.assert_not_awaited()
        due.event.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_turning_it_off_drops_a_running_clock(self, ctx):
        scheduler = new_scheduler(ctx)
        item = await add_item(ctx, "Lamp", printer_id=1, manual_start=True, filament_short=True)
        await one_pass(ctx, scheduler, deficits={item: DEFICIT})
        assert "1" in await saved(ctx)

        await _set_setting(ctx, "queue_loaded_filament_first", "false")
        at(ctx, 400)
        due = await one_pass(ctx, scheduler, deficits={item: DEFICIT})

        due.event.assert_not_awaited()
        assert await saved(ctx) == {}


class TestAnyModelJob:
    @pytest.mark.asyncio
    async def test_any_model_job_sends_one_message_per_idle_printer(self, ctx):
        """Five idle P1S, one "Any P1S" job lacking PETG on each: five messages, each naming its printer and what it lacks."""
        async with ctx.session_maker() as db:
            db.add_all(
                Printer(
                    id=pid,
                    name=f"P1S {pid}",
                    serial_number=f"SN000{pid}",
                    ip_address=f"10.0.0.{pid}",
                    access_code="x",
                    model="P1S",
                    is_active=True,
                )
                for pid in (4, 5, 6)
            )
            await db.commit()
        scheduler = new_scheduler(ctx)
        await add_item(ctx, "Any P1S job", target_model="P1S", required_filament_types=PETG_ONLY)

        due = await pass_pair(ctx, scheduler, trays=dict.fromkeys(range(1, 7), PLA_TRAYS))

        assert announced_printers(due) == [1, 2, 4, 5, 6]
        names = {call.args[0]: call.args[1] for call in due.event.await_args_list}
        assert names == {1: "P1S right", 2: "P1S left", 4: "P1S 4", 5: "P1S 5", 6: "P1S 6"}
        for call in due.event.await_args_list:
            (job,) = call.args[2]
            assert job.name == "Any P1S job"
            assert [n.filament.type for n in job.needs] == ["PETG"]


async def _set_setting(ctx, key, value):
    async with ctx.session_maker() as db:
        row = (await db.execute(select(Settings).where(Settings.key == key))).scalar_one_or_none()
        if row is None:
            db.add(Settings(key=key, value=value))
        else:
            row.value = value
        await db.commit()
