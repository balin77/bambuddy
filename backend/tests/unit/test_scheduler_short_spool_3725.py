"""A spool that is too short is reported at once, also with Loaded filament first (#3725).

The mode skips a job for filament quietly until its maximum wait is up. A short
spool does not resolve by itself, so the job's waiting notification goes out the
first time the job is found to wait for it, once per job and spool, in the
sentence of #3642. What is only missing keeps waiting for its priority.
"""

import json
from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import update

from backend.app.models.print_queue import PrintQueueItem
from backend.app.models.settings import Settings
from backend.app.services.filament_deficit import FilamentDeficit
from backend.app.services.filament_idle_watch import SETTING_KEY
from backend.app.services.print_scheduler import PrintScheduler
from backend.tests.unit.test_scheduler_idle_for_filament_3725 import (
    DEFICIT,
    PETG,
    T0,
    add_item,
    at,
    ctx,  # noqa: F401 - fixture
    new_scheduler,
    one_pass,
    saved_raw,
)

SENTENCE = "Not enough PLA on P1S right: A3 has 196 g, the job needs 505 g"


def _reasons(waiting) -> list[str]:
    return [call.kwargs["waiting_reason"] for call in waiting.await_args_list]


async def _max_wait(ctx, value):
    from sqlalchemy import select

    async with ctx.session_maker() as db:
        row = (await db.execute(select(Settings).where(Settings.key == "queue_max_wait_hours"))).scalar_one()
        row.value = value
        await db.commit()


class TestPinned:
    @pytest.mark.asyncio
    async def test_told_at_once_with_the_sentence_and_only_once(self, ctx):
        scheduler = new_scheduler(ctx)
        item = await add_item(ctx, "Lamp", printer_id=1)

        first = await one_pass(ctx, scheduler, deficits={item: DEFICIT})
        second = await one_pass(ctx, scheduler, deficits={item: DEFICIT})

        assert _reasons(first.waiting) == [SENTENCE]
        kwargs = first.waiting.await_args.kwargs
        assert (kwargs["job_name"], kwargs["printer_id"], kwargs["target_model"]) == ("Lamp", 1, "P1S")
        assert [(f.type, f.slot) for f in kwargs["filaments"]] == [("PLA", "A3")]
        second.waiting.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_without_a_maximum_wait_the_start_message_is_not_a_second_one(self, ctx):
        await _max_wait(ctx, "None")
        scheduler = new_scheduler(ctx)
        item = await add_item(ctx, "Lamp", printer_id=1)

        first = await one_pass(ctx, scheduler, deficits={item: DEFICIT})
        second = await one_pass(ctx, scheduler, deficits={item: DEFICIT})

        assert _reasons(first.waiting) == [SENTENCE]
        second.waiting.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_the_priority_message_still_comes_later(self, ctx):
        scheduler = new_scheduler(ctx)
        item = await add_item(ctx, "Lamp", printer_id=1)
        first = await one_pass(ctx, scheduler, deficits={item: DEFICIT})
        async with ctx.session_maker() as db:
            await db.execute(
                update(PrintQueueItem)
                .where(PrintQueueItem.id == item)
                .values(created_at=T0.replace(tzinfo=None) - timedelta(hours=100))
            )
            await db.commit()

        later = await one_pass(ctx, scheduler, deficits={item: DEFICIT})

        assert _reasons(first.waiting) == [SENTENCE]
        (priority,) = _reasons(later.waiting)
        assert priority.startswith("Waiting for filament: PLA (196 g left, needs 505 g)")
        assert priority.endswith("has priority")

    @pytest.mark.asyncio
    async def test_another_short_spool_is_told_too(self, ctx):
        scheduler = new_scheduler(ctx)
        item = await add_item(ctx, "Lamp", printer_id=1)
        await one_pass(ctx, scheduler, deficits={item: DEFICIT})

        other = await one_pass(ctx, scheduler, deficits={item: [*DEFICIT, *PETG]})

        (reason,) = _reasons(other.waiting)
        assert reason == (
            "Not enough filament on P1S right: PLA A3 has 196 g, the job needs 505 g; PETG A2 has 10 g, the job needs 90 g"
        )

    @pytest.mark.asyncio
    async def test_a_filament_that_is_only_missing_waits_for_its_priority(self, ctx):
        scheduler = new_scheduler(ctx)
        item = await add_item(ctx, "Lamp", printer_id=1)
        brown = [{"slot_id": 1, "type": "PLA", "color": "#7D6556", "color_name": "Army Beige"}]

        result = await one_pass(ctx, scheduler, unmatched={item: brown})

        result.waiting.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_busy_printer_is_silent(self, ctx):
        scheduler = new_scheduler(ctx)
        item = await add_item(ctx, "Lamp", printer_id=1)

        result = await one_pass(ctx, scheduler, deficits={item: DEFICIT}, idle=lambda pid: False, state="RUNNING")

        result.waiting.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_print_anyway_is_silent(self, ctx):
        scheduler = new_scheduler(ctx)
        item = await add_item(ctx, "Lamp", printer_id=1, skip_filament_check=True)

        result = await one_pass(ctx, scheduler, deficits={item: DEFICIT})

        result.waiting.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_restart_does_not_tell_again_what_the_saved_reason_shows(self, ctx):
        item = await add_item(
            ctx,
            "Lamp",
            printer_id=1,
            waiting_reason="Waiting for filament: PLA (196 g left, needs 505 g) · priority in 5 h",
        )

        result = await one_pass(ctx, PrintScheduler(), deficits={item: DEFICIT})

        result.waiting.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_the_mode_off_still_sends_one_message_from_the_deficit_gate(self, ctx):
        await _mode_off(ctx)
        scheduler = new_scheduler(ctx)
        item = await add_item(ctx, "Lamp", printer_id=1)

        result = await one_pass(ctx, scheduler, deficits={item: DEFICIT})
        again = await one_pass(ctx, scheduler, deficits={item: DEFICIT})

        assert _reasons(result.waiting) == [SENTENCE]
        again.waiting.assert_not_awaited()


class TestModelJobs:
    @pytest.mark.asyncio
    async def test_told_once_for_the_first_printer_that_is_short(self, ctx):
        scheduler = new_scheduler(ctx)
        await add_item(ctx, "Lamp", target_model="P1S")

        first = await one_pass(ctx, scheduler, short={1, 2})
        second = await one_pass(ctx, scheduler, short={1, 2})

        sentences = [r for r in _reasons(first.waiting) if r.startswith("Not enough")]
        assert sentences == [SENTENCE]
        assert first.waiting.await_args_list[0].kwargs["printer_id"] == 1
        assert not [r for r in _reasons(second.waiting) if r.startswith("Not enough")]

    @pytest.mark.asyncio
    async def test_a_busy_short_printer_is_silent(self, ctx):
        scheduler = new_scheduler(ctx)
        await add_item(ctx, "Lamp", target_model="P1S")

        result = await one_pass(ctx, scheduler, short={1, 2}, idle=lambda pid: False, state="RUNNING")

        assert not [r for r in _reasons(result.waiting) if r.startswith("Not enough")]

    @pytest.mark.asyncio
    async def test_another_printer_being_short_is_not_a_second_notice(self, ctx):
        scheduler = new_scheduler(ctx)
        item = await add_item(ctx, "Lamp", target_model="P1S")
        await one_pass(ctx, scheduler, short={1, 2})
        async with ctx.session_maker() as db:  # the saved reason must not be what keeps it quiet
            (await db.get(PrintQueueItem, item)).waiting_reason = None
            await db.commit()

        other = await one_pass(ctx, scheduler, short={2}, idle=lambda pid: pid != 1)

        assert not [r for r in _reasons(other.waiting) if r.startswith("Not enough")]

    @pytest.mark.asyncio
    async def test_a_restart_during_a_busy_phase_does_not_tell_again(self, ctx):
        scheduler = new_scheduler(ctx)
        item = await add_item(ctx, "Lamp", printer_id=1)
        first = await one_pass(ctx, scheduler, deficits={item: DEFICIT})
        await one_pass(ctx, scheduler, deficits={item: DEFICIT}, idle=lambda pid: False, state="RUNNING")

        restarted = await one_pass(ctx, new_scheduler(ctx), deficits={item: DEFICIT})

        assert _reasons(first.waiting) == [SENTENCE]
        restarted.waiting.assert_not_awaited()
        assert "short" in await saved_raw(ctx)


class TestWithTheIdleMessage:
    @pytest.mark.asyncio
    async def test_the_idle_message_waits_a_pass_for_a_job_just_told(self, ctx):
        """The five minutes were already up when the short spool was found: the printer is told the pass after."""
        item = await add_item(ctx, "Lamp", printer_id=1)
        async with ctx.session_maker() as db:
            db.add(
                Settings(
                    key=SETTING_KEY,
                    value=json.dumps({"1": {"since": (T0 - timedelta(hours=1)).isoformat(), "announced": None}}),
                )
            )
            await db.commit()
        scheduler = new_scheduler(ctx)

        first = await one_pass(ctx, scheduler, deficits={item: DEFICIT})
        at(ctx, 30)
        second = await one_pass(ctx, scheduler, deficits={item: DEFICIT})

        assert _reasons(first.waiting) == [SENTENCE]
        first.event.assert_not_awaited()
        second.event.assert_awaited_once()
        second.waiting.assert_not_awaited()


async def _mode_off(ctx):
    from sqlalchemy import select

    async with ctx.session_maker() as db:
        row = (await db.execute(select(Settings).where(Settings.key == "queue_loaded_filament_first"))).scalar_one()
        row.value = "false"
        await db.commit()
