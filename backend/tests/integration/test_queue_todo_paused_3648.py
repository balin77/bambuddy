"""GET /queue/todo lists a paused print and why it waits (#3648)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from backend.app.api.routes import print_queue as queue_routes
from backend.app.services.bambu_mqtt import HMSError, PrinterState
from backend.app.services.printer_manager import printer_manager
from backend.app.services.queue_todo import PauseEpisodes
from backend.tests.integration.test_queue_todo_3615 import (  # noqa: F401 - fixtures
    URL,
    TestTodoAccess,
    _auth,
    _only_entries,
    _quiet_scheduler_state,
    make_item,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


@pytest.fixture(autouse=True)
def _fresh_episodes():
    with patch.object(queue_routes, "_pause_episodes", PauseEpisodes()):
        yield


def _runout_state(**changes) -> PrinterState:
    state = PrinterState(
        connected=True,
        state="PAUSE",
        subtask_name="Benchy",
        subtask_id="42",
        progress=42.0,
        remaining_time=95,
        tray_tar=1,
        tray_pre=0,
        raw_data={
            "ams": [
                {
                    "id": 0,
                    "tray": [
                        {"id": 0, "tray_type": "PLA", "tray_color": "C12E1FFF", "tray_info_idx": "GFA00"},
                        {"id": 1, "tray_type": "", "tray_color": "00000000"},
                    ],
                }
            ],
            "vt_tray": [],
        },
        hms_errors=[
            HMSError(
                code="0x8011",
                attr=0x07000000,
                module=7,
                severity=2,
                description="AMS A filament ran out",
                full_code="0700000000018011",
            )
        ],
    )
    for key, value in changes.items():
        setattr(state, key, value)
    return state


def _serve(states: dict[int, PrinterState]):
    return patch.object(printer_manager, "get_status", lambda pid: states.get(pid))


class TestPausedEntry:
    async def test_a_paused_printer_with_a_runout_is_listed_without_a_waiting_job(self, async_client, printer_factory):
        a = await printer_factory(name="A", model="X1C")
        with _serve({a.id: _runout_state()}):
            body = (await async_client.get(URL)).json()
        assert body["count"] == 1
        entry = _only_entries(body)[0]
        assert entry["kind"] == "print_paused"
        assert entry["jobs"] == []
        paused = entry["paused"]
        assert (paused["job_name"], paused["progress"], paused["remaining_minutes"]) == ("Benchy", 42, 95)
        assert paused["cause"] == "runout_ams"
        assert (paused["ran_out"]["ams_id"], paused["ran_out"]["tray_id"], paused["ran_out"]["type"]) == (0, 0, "PLA")
        assert paused["ran_out"]["color"] == "#C12E1F"
        assert (paused["expected"]["tray_id"], paused["expected"]["type"]) == (1, "")

    async def test_an_error_names_its_description(self, async_client, printer_factory):
        a = await printer_factory(name="A", model="X1C")
        state = _runout_state(
            hms_errors=[
                HMSError(
                    code="0x0006",
                    attr=0x05000100,
                    module=5,
                    severity=1,
                    description="The door is open",
                    full_code="0500010000010006",
                )
            ]
        )
        with _serve({a.id: state}):
            paused = _only_entries((await async_client.get(URL)).json())[0]["paused"]
        assert paused["cause"] == "error"
        assert paused["error"] == {"code": "0500-0100-0001-0006", "description": "The door is open"}

    async def test_a_pause_without_a_reason(self, async_client, printer_factory):
        a = await printer_factory(name="A", model="X1C")
        with _serve({a.id: _runout_state(hms_errors=[])}):
            paused = _only_entries((await async_client.get(URL)).json())[0]["paused"]
        assert paused["cause"] == "paused"
        assert paused["error"] is None

    async def test_a_printer_that_is_not_paused_is_not_listed(self, async_client, printer_factory):
        a = await printer_factory(name="A", model="X1C")
        with _serve({a.id: _runout_state(state="RUNNING")}):
            assert (await async_client.get(URL)).json() == {"count": 0, "groups": []}

    async def test_an_offline_printer_is_not_listed(self, async_client, printer_factory):
        a = await printer_factory(name="A", model="X1C")
        with _serve({a.id: _runout_state(connected=False)}):
            assert (await async_client.get(URL)).json() == {"count": 0, "groups": []}

    async def test_waiting_jobs_are_listed_under_the_paused_entry(self, async_client, printer_factory, make_item):
        a = await printer_factory(name="A", model="X1C")
        await make_item(a.id, name="Next up")
        with _serve({a.id: _runout_state()}):
            body = (await async_client.get(URL)).json()
        entry = _only_entries(body)[0]
        assert entry["kind"] == "print_paused"
        assert [j["name"] for j in entry["jobs"]] == ["Next up"]

    async def test_the_cause_survives_a_rebuilt_empty_fault_list(self, async_client, printer_factory):
        a = await printer_factory(name="A", model="X1C")
        with _serve({a.id: _runout_state()}):
            first = _only_entries((await async_client.get(URL)).json())[0]["paused"]
        with _serve({a.id: _runout_state(hms_errors=[])}):
            second = _only_entries((await async_client.get(URL)).json())[0]["paused"]
        with _serve({a.id: _runout_state(state="RUNNING")}):
            await async_client.get(URL)
        with _serve({a.id: _runout_state(hms_errors=[])}):
            after = _only_entries((await async_client.get(URL)).json())[0]["paused"]
        assert first["cause"] == second["cause"] == "runout_ams"
        assert after["cause"] == "paused"


class TestPausedAccess:
    async def test_the_job_name_needs_printers_read(self, async_client, printer_factory):
        a = await printer_factory(name="A", model="X1C")
        helper = TestTodoAccess()
        _, member = await helper._setup(async_client, ["queue:read_all"], printer_ids=[a.id])
        with _serve({a.id: _runout_state()}):
            paused = _only_entries((await async_client.get(URL, headers=_auth(member))).json())[0]["paused"]
        assert paused["job_name"] is None
        assert paused["cause"] == "runout_ams"

    async def test_the_job_name_is_shown_with_printers_read(self, async_client, printer_factory):
        a = await printer_factory(name="A", model="X1C")
        helper = TestTodoAccess()
        _, member = await helper._setup(async_client, ["queue:read_all", "printers:read"], printer_ids=[a.id])
        with _serve({a.id: _runout_state()}):
            paused = _only_entries((await async_client.get(URL, headers=_auth(member))).json())[0]["paused"]
        assert paused["job_name"] == "Benchy"

    async def test_a_printer_outside_the_scope_is_not_listed(self, async_client, printer_factory):
        a = await printer_factory(name="A", model="X1C")
        b = await printer_factory(name="B", model="X1C")
        helper = TestTodoAccess()
        _, member = await helper._setup(async_client, ["queue:read_all", "printers:read"], printer_ids=[a.id])
        with _serve({a.id: _runout_state(), b.id: _runout_state(subtask_name="Secret")}):
            body = (await async_client.get(URL, headers=_auth(member))).json()
        assert [g["printer_id"] for g in body["groups"]] == [a.id]
        assert body["count"] == 1


class TestRunoutPicture:
    """The runout's AMS picture: the slot that ran out and the filament the print needs there (#3726)."""

    @staticmethod
    def _a1_runout(**changes) -> PrinterState:
        # An A1 with its AMS Lite: A4 ran out, the printer reports only the hms[] fault.
        state = _runout_state(
            tray_tar=None,
            tray_pre=None,
            print_ams_mapping=[0, 3],
            raw_data={
                "ams": [
                    {
                        "id": 0,
                        "info": "1002",
                        "tray": [
                            {"id": 0, "tray_type": "PLA", "tray_color": "FFFFFFFF"},
                            {"id": 1, "tray_type": "PLA", "tray_color": "000000FF"},
                            {"id": 2, "tray_type": "PETG", "tray_color": "00FF00FF"},
                            {"id": 3, "tray_type": "", "tray_color": "00000000", "state": 9},
                        ],
                    }
                ],
                "vt_tray": [{"id": 254, "tray_type": ""}],
            },
            hms_errors=[
                HMSError(
                    code="0x00020001",
                    attr=0x12002300,
                    module=0x12,
                    severity=2,
                    description="AMS A Slot4 filament has run out; please insert a new filament.",
                    full_code="1200230000020001",
                )
            ],
        )
        for key, value in changes.items():
            setattr(state, key, value)
        return state

    async def test_the_slot_that_ran_out_carries_the_queue_jobs_filament(
        self, async_client, printer_factory, make_item
    ):
        from unittest.mock import AsyncMock

        from backend.app.services.print_scheduler import scheduler

        a = await printer_factory(name="A1 rechts", model="A1")
        await make_item(
            a.id,
            name="hello_kitty",
            status="printing",
            ams_mapping="[0, 3]",
            filament_overrides='[{"slot_id": 2, "type": "PLA", "color": "#F5A9B8", "color_name": "Pink"}]',
        )
        requirements = [
            {"slot_id": 1, "type": "PLA", "color": "#FFFFFF"},
            {"slot_id": 2, "type": "PLA", "color": "#000000"},
        ]
        with (
            _serve({a.id: self._a1_runout()}),
            patch.object(scheduler, "_get_filament_requirements", AsyncMock(return_value=requirements)),
        ):
            body = (await async_client.get(URL)).json()
        paused = _only_entries(body)[0]["paused"]
        assert paused["cause"] == "runout_ams"
        slots = {(s["ams_id"], s["tray_id"]): s for u in paused["ams_picture"]["units"] for s in u["slots"]}
        assert slots[(0, 3)]["state"] == "ran_out"
        assert slots[(0, 3)]["incoming"]["color"] == "#F5A9B8"
        assert slots[(0, 3)]["incoming"]["color_name"] == "Pink"
        assert [s["state"] for key, s in slots.items() if key != (0, 3)].count("ran_out") == 0
        assert paused["filaments"] == [
            {
                "type": "PLA",
                "color": "#F5A9B8",
                "color_name": "Pink",
                "no_stock": False,
                "nozzle": None,
                "short": False,
                "short_trays": [],
                "required_grams": None,
            }
        ]

    async def test_a_plain_pause_has_no_picture(self, async_client, printer_factory):
        a = await printer_factory(name="A", model="X1C")
        with _serve({a.id: _runout_state(hms_errors=[])}):
            body = (await async_client.get(URL)).json()
        paused = _only_entries(body)[0]["paused"]
        assert paused["cause"] == "paused"
        assert paused["ams_picture"] is None
