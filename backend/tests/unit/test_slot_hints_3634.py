"""Which slot a missing filament can go into (#3634)."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.tests.unit.test_ams_mapping_per_printer_2799 import (
    P2S_4_TRAYS,
    P2S_5_TRAYS,
    SHARED_MAPPING,
    _item,
    _scheduler,
)


def _planning_scheduler(trays, requirements=None):
    scheduler = _scheduler(trays) if requirements is None else _scheduler(trays, requirements)
    scheduler._get_bool_setting = AsyncMock(return_value=False)
    scheduler._creator_filament_scope = AsyncMock(return_value=MagicMock(is_unrestricted=True))
    return scheduler


class TestPlannedMapping:
    """``_planned_mapping`` is what ``missing_filament_for_start`` reads: no new behaviour."""

    @pytest.mark.asyncio
    async def test_a_stored_mapping_that_fits_is_kept(self):
        scheduler = _scheduler(P2S_4_TRAYS)
        with patch("backend.app.services.print_scheduler.printer_manager") as pm:
            pm.get_status.return_value = MagicMock()
            mapping = await scheduler._planned_mapping(AsyncMock(), _item(), 9)
        assert mapping == SHARED_MAPPING

    @pytest.mark.asyncio
    async def test_a_stored_mapping_that_conflicts_is_matched_afresh(self):
        # The mapping was resolved on another printer: here slot 3 would get ASA.
        scheduler = _planning_scheduler(P2S_5_TRAYS)
        with patch("backend.app.services.print_scheduler.printer_manager") as pm:
            pm.get_status.return_value = MagicMock()
            mapping = await scheduler._planned_mapping(AsyncMock(), _item(), 8)
        assert mapping[0] == 0
        assert mapping[2] == 2

    @pytest.mark.asyncio
    async def test_no_stored_mapping_is_matched(self):
        scheduler = _planning_scheduler(P2S_5_TRAYS)
        with patch("backend.app.services.print_scheduler.printer_manager") as pm:
            pm.get_status.return_value = MagicMock()
            mapping = await scheduler._planned_mapping(AsyncMock(), _item(ams_mapping=None), 8)
        assert (mapping[0], mapping[2]) == (0, 2)

    @pytest.mark.asyncio
    async def test_an_unreadable_stored_mapping_is_matched_and_nothing_to_match_is_empty(self):
        scheduler = _planning_scheduler(P2S_5_TRAYS, requirements=[])
        with patch("backend.app.services.print_scheduler.printer_manager") as pm:
            pm.get_status.return_value = MagicMock()
            mapping = await scheduler._planned_mapping(AsyncMock(), _item(ams_mapping="not json"), 8)
        assert mapping == []

    @pytest.mark.asyncio
    async def test_the_pass_memos_are_left_alone(self):
        scheduler = _scheduler(P2S_5_TRAYS)
        scheduler._filament_req_memo[("kept",)] = [{"slot_id": 1}]
        with patch("backend.app.services.print_scheduler.printer_manager") as pm:
            pm.get_status.return_value = MagicMock()
            await scheduler._planned_mapping(AsyncMock(), _item(ams_mapping=json.dumps([0, -1, 2])), 8)
        assert scheduler._filament_req_memo[("kept",)] == [{"slot_id": 1}]
