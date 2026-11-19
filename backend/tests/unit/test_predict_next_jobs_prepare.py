"""Which jobs come next on a printer (#3640): the prediction behind the To do list's Prepare lines."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.app.services.print_scheduler import PrintScheduler, predict_next_jobs

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def _item(item_id, printer_id=1, scheduled=None, status="pending", **fields):
    item = MagicMock()
    item.id = item_id
    item.printer_id = printer_id
    item.status = status
    item.scheduled_time = scheduled
    item.target_model = None
    item.variants = []
    item.created_by_id = None
    for key, value in fields.items():
        setattr(item, key, value)
    return item


def _go(*items, extra=None):
    could = {i.id: ({i.printer_id} if i.printer_id else set()) for i in items}
    could.update(extra or {})
    return could


def _ids(jobs):
    return [j.id for j in jobs]


class TestPredictNextJobs:
    def test_jobs_come_in_the_order_of_the_pass(self):
        items = [_item(3), _item(1), _item(2)]
        out = predict_next_jobs(1, items, _go(*items), set(), NOW, 600)
        assert _ids(out.candidates) == [3, 1, 2]

    def test_a_job_pinned_to_another_printer_is_not_a_candidate(self):
        items = [_item(1), _item(2, printer_id=2)]
        assert _ids(predict_next_jobs(1, items, _go(*items), set(), NOW, 600).candidates) == [1]

    def test_a_model_job_only_this_printer_can_take_is_a_candidate(self):
        model = _item(2, printer_id=None, target_model="X1C")
        items = [model]
        assert _ids(predict_next_jobs(1, items, {2: {1}}, set(), NOW, 600).candidates) == [2]

    def test_a_model_job_several_printers_could_take_is_left_out(self):
        model = _item(2, printer_id=None, target_model="X1C")
        assert predict_next_jobs(1, [model], {2: {1, 3}}, set(), NOW, 600).candidates == ()

    def test_a_job_that_is_not_pending_is_left_out(self):
        items = [_item(1, status="skipped"), _item(2)]
        assert _ids(predict_next_jobs(1, items, _go(*items), set(), NOW, 600).candidates) == [2]

    def test_a_staged_job_counts(self):
        items = [_item(1, manual_start=True)]
        assert _ids(predict_next_jobs(1, items, _go(*items), set(), NOW, 600).candidates) == [1]

    def test_a_held_job_is_no_candidate_but_is_kept_apart(self):
        items = [_item(1), _item(2)]
        out = predict_next_jobs(1, items, _go(*items), {1}, NOW, 600)
        assert (_ids(out.held), _ids(out.candidates)) == ([1], [2])

    def test_a_model_job_held_on_this_printer_is_kept_even_when_others_could_take_it(self):
        model = _item(2, printer_id=None, target_model="X1C")
        out = predict_next_jobs(1, [model], {2: {1, 3}}, {2}, NOW, 600)
        assert _ids(out.held) == [2]

    def test_a_future_job_due_before_the_print_ends_is_a_candidate(self):
        due = _item(1, scheduled=NOW + timedelta(minutes=5))
        later = _item(2, scheduled=NOW + timedelta(minutes=30))
        items = [due, later]
        out = predict_next_jobs(1, items, _go(*items), set(), NOW, 600)
        assert _ids(out.candidates) == [1]

    def test_a_future_job_is_skipped_when_the_end_is_unknown(self):
        items = [_item(1, scheduled=NOW + timedelta(minutes=5)), _item(2)]
        assert _ids(predict_next_jobs(1, items, _go(*items), set(), NOW, None).candidates) == [2]

    def test_a_naive_stored_time_is_read_as_utc(self):
        naive = (NOW + timedelta(minutes=5)).replace(tzinfo=None)
        items = [_item(1, scheduled=naive)]
        assert _ids(predict_next_jobs(1, items, _go(*items), set(), NOW, 600).candidates) == [1]
        assert predict_next_jobs(1, items, _go(*items), set(), NOW, 60).candidates == ()

    def test_a_job_already_due_is_a_candidate_even_with_nothing_running(self):
        items = [_item(1, scheduled=NOW - timedelta(minutes=1))]
        assert _ids(predict_next_jobs(1, items, _go(*items), set(), NOW, 0).candidates) == [1]


class TestCouldGoByItem:
    @pytest.mark.asyncio
    async def test_pinned_and_model_jobs_and_nothing_else(self):
        scheduler = PrintScheduler()
        scheduler._creator_printer_scope = AsyncMock(return_value=MagicMock())
        scheduler._model_job_printer_ids = AsyncMock(return_value={4, 5})
        pinned = _item(1, printer_id=7)
        model = _item(2, printer_id=None, target_model="X1C")
        skipped = _item(3, status="skipped")
        neither = _item(4, printer_id=None)
        with patch("backend.app.services.print_scheduler.printer_manager"):
            out = await scheduler._could_go_by_item(AsyncMock(), [pinned, model, skipped, neither])
        assert out == {1: {7}, 2: {4, 5}}
