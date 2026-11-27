"""A paused print whose filament ran out shows the AMS picture with what goes where (#3648, #3726)."""

from types import SimpleNamespace

from backend.app.schemas.print_queue import QueueTodoResponse
from backend.app.services.print_scheduler import _picture_slots
from backend.app.services.queue_todo import (
    CAUSE_ERROR,
    CAUSE_RUNOUT_AMS,
    CAUSE_RUNOUT_EXTERNAL,
    PICTURE_RAN_OUT,
    HmsRunout,
    PauseCause,
    PausedInfo,
    PausedSlot,
    SlotExtra,
    TodoFilament,
    build_todo,
    hms_runout,
    pause_cause,
    runout_picture,
)


def _hms(full_code, description="Filament has run out", severity=2):
    attr, code = int(full_code[:8], 16), int(full_code[8:], 16)
    return {
        "attr": attr,
        "code": f"0x{code:08X}",
        "severity": severity,
        "description": description,
        "full_code": full_code,
        "actions": [],
    }


def _tray(tray_id, kind="", color="", **extra):
    return {"id": tray_id, "tray_type": kind, "tray_color": color, **extra}


def _status(ams, vt_tray=None):
    """A printer state as ``_picture_slots`` reads it."""
    return SimpleNamespace(
        raw_data={"ams": ams, "vt_tray": vt_tray if vt_tray is not None else [{"id": 254}]},
        ams_extruder_map={},
        extruder_slots={},
        tray_now=255,
        fila_switch=None,
        model="A1",
    )


# An A1 with its AMS Lite (unit 0): A4 ran out, the others are loaded.
A1_LITE = [
    {
        "id": 0,
        # Bits 0-3 of ``info``: an AMS Lite.
        "info": "1002",
        "tray": [
            _tray(0, "PLA", "FFFFFFFF"),
            _tray(1, "PLA", "000000FF"),
            _tray(2, "PETG", "00FF00FF"),
            _tray(3, state=9),
        ],
    }
]
LITE_A4_RUNOUT = _hms("1200230000020001", "AMS A Slot4 filament has run out; please insert a new filament.")
LITE_A2_RUNOUT = _hms("1200210000020001", "AMS A Slot2 filament has run out; please insert a new filament.")
PINK = TodoFilament("PLA", "#F5A9B8", tray_info_idx="GFA00")


def _slots(ams=A1_LITE, vt_tray=None):
    return _picture_slots(_status(ams, vt_tray))


def _info(faults, *, ams=A1_LITE, vt_tray=None, needs=None, ran_out=None, expected=None):
    return PausedInfo(
        "hello_kitty.4x.A1.swap.jobox",
        15,
        838,
        pause_cause(faults, expected=expected, ran_out=ran_out),
        slots=_slots(ams, vt_tray),
        needs=needs or {},
    )


def _slot_states(picture):
    return {(s["ams_id"], s["tray_id"]): s["state"] for u in picture["units"] for s in u["slots"]}


def _incoming(picture):
    return {(s["ams_id"], s["tray_id"]): s["incoming"] for u in picture["units"] for s in u["slots"] if s["incoming"]}


class TestHmsRunout:
    def test_the_slot_of_an_ams_lite_runout(self):
        assert hms_runout(LITE_A4_RUNOUT) == HmsRunout(0x12, 0, 3)

    def test_an_ams_and_an_ams_ht_and_an_external_runout(self):
        assert hms_runout(_hms("0701200000020001")) == HmsRunout(0x07, 1, 0)
        assert hms_runout(_hms("1800200000020001")) == HmsRunout(0x18, 0, 0)
        external = hms_runout(_hms("07FF200000020001"))
        assert external == HmsRunout(0x07, 0xFF, 0) and external.external

    def test_other_faults_of_the_same_unit_are_no_runout(self):
        # Purging the old filament, and the backup that already switched over.
        assert hms_runout(_hms("1200230000030001")) is None
        assert hms_runout(_hms("1200230000030002")) is None
        assert hms_runout(_hms("0700800000010001")) is None
        assert hms_runout({"full_code": "07008011"}) is None


class TestPauseCause:
    def test_an_hms_runout_alone_is_an_ams_runout_not_an_error(self):
        # The A1 reports only the hms[] fault: it used to read as an error with the HMS text.
        cause = pause_cause([LITE_A4_RUNOUT])
        assert cause.cause == CAUSE_RUNOUT_AMS
        assert cause.runouts == (HmsRunout(0x12, 0, 3),)
        assert cause.more_errors == 0

    def test_two_slots_that_ran_out_are_both_kept(self):
        cause = pause_cause([LITE_A4_RUNOUT, LITE_A2_RUNOUT])
        assert [r.slot for r in cause.runouts] == [3, 1]
        assert cause.more_errors == 0

    def test_an_external_hms_runout_is_the_external_spools(self):
        cause = pause_cause([_hms("12FF200000020001")])
        assert cause.cause == CAUSE_RUNOUT_EXTERNAL

    def test_another_fault_still_counts(self):
        door = _hms("0500010000010006", "The door is open", severity=1)
        cause = pause_cause([LITE_A4_RUNOUT, door])
        assert (cause.cause, cause.more_errors) == (CAUSE_RUNOUT_AMS, 1)

    def test_without_a_runout_an_error_stays_an_error(self):
        assert pause_cause([_hms("0500010000010006", "The door is open", severity=1)]).cause == CAUSE_ERROR


class TestRunoutPicture:
    def test_the_slot_that_ran_out_gets_the_filament_the_print_needs(self):
        # The print loads pink PLA from global tray 3 (A4).
        info = _info([LITE_A4_RUNOUT], needs={3: PINK})
        picture, filaments = runout_picture(info, 1, "A1 rechts")
        assert filaments == [PINK]
        states = _slot_states(picture)
        assert states[(0, 3)] == PICTURE_RAN_OUT
        assert [k for k, s in states.items() if s == PICTURE_RAN_OUT] == [(0, 3)]
        incoming = _incoming(picture)
        assert list(incoming) == [(0, 3)]
        assert incoming[(0, 3)]["type"] == "PLA"
        assert incoming[(0, 3)]["color"] == "#F5A9B8"
        assert incoming[(0, 3)]["filament_index"] == 0
        # One picture, the AMS Lite open.
        assert [u["collapsed"] for u in picture["units"]] == [False, True]
        assert picture["unplaced"] == []

    def test_two_slots_in_one_picture_each_with_its_filament(self):
        black = TodoFilament("PLA", "#000000")
        info = _info([LITE_A4_RUNOUT, LITE_A2_RUNOUT], needs={3: PINK, 1: black})
        picture, filaments = runout_picture(info, 1, "A1 rechts")
        states = _slot_states(picture)
        assert sorted(k for k, s in states.items() if s == PICTURE_RAN_OUT) == [(0, 1), (0, 3)]
        incoming = _incoming(picture)
        assert filaments[incoming[(0, 1)]["filament_index"]] == black
        assert filaments[incoming[(0, 3)]["filament_index"]] == PINK

    def test_without_the_prints_filament_the_tray_it_still_reports_is_used(self):
        # A2 ran out but still reports black PLA, and nothing is known of the file.
        picture, filaments = runout_picture(_info([LITE_A2_RUNOUT]), 1, "A1 rechts")
        assert [(f.type, f.color) for f in filaments] == [("PLA", "#000000")]
        assert _incoming(picture)[(0, 1)]["type"] == "PLA"

    def test_an_unknown_filament_leaves_the_slot_run_out_without_a_card(self):
        picture, filaments = runout_picture(_info([LITE_A4_RUNOUT]), 1, "A1 rechts")
        assert filaments == []
        assert _slot_states(picture)[(0, 3)] == PICTURE_RAN_OUT
        assert _incoming(picture) == {}

    def test_the_slot_the_printer_left_counts_without_an_hms_fault(self):
        # Only the print_error (0700_8011): the slot is the one the printer left (tray_pre).
        print_error = {"attr": 0x07000000, "code": "0x8011", "severity": 2, "description": "", "full_code": "07008011"}
        left = PausedSlot(0, 2, False, False, 1, "PETG", "#00FF00")
        picture, filaments = runout_picture(_info([print_error], ran_out=left, needs={2: PINK}), 1, "A1")
        assert _slot_states(picture)[(0, 2)] == PICTURE_RAN_OUT
        assert filaments == [PINK]

    def test_the_external_spool(self):
        # A printer without an AMS: the external holder is the picture, its spool ran out.
        vt = [{"id": 254, "tray_type": "", "tray_color": ""}]
        info = _info([_hms("12FF200000020001")], ams=[], vt_tray=vt, needs={254: PINK})
        picture, filaments = runout_picture(info, 1, "A1 mini")
        assert [u["kind"] for u in picture["units"]] == ["external"]
        assert _slot_states(picture) == {(255, 0): PICTURE_RAN_OUT}
        assert _incoming(picture)[(255, 0)]["type"] == "PLA"
        assert filaments == [PINK]

    def test_the_external_spool_of_a_printer_with_an_ams(self):
        vt = [{"id": 254, "tray_type": "PETG", "tray_color": "112233FF"}]
        info = _info([{"attr": 0x03000000, "code": "0x8004", "severity": 2, "full_code": "03008004"}], vt_tray=vt)
        picture, _ = runout_picture(info, 1, "X1C")
        assert _slot_states(picture)[(255, 0)] == PICTURE_RAN_OUT
        assert [u["kind"] for u in picture["units"] if not u["collapsed"]] == ["external"]
        assert _incoming(picture)[(255, 0)]["color"] == "#112233"

    def test_no_picture_for_a_pause_that_is_no_runout(self):
        door = _hms("0500010000010006", "The door is open", severity=1)
        assert runout_picture(_info([door]), 1, "A1") == (None, [])

    def test_no_picture_when_the_printer_reports_no_slots(self):
        info = PausedInfo("x", 1, 1, pause_cause([LITE_A4_RUNOUT]))
        assert runout_picture(info, 1, "A1") == (None, [])

    def test_the_inventory_and_the_stock_are_carried(self):
        extras = {(1, 0, 0): SlotExtra(remaining_grams=420.0, color_name="Jade White")}
        info = _info([LITE_A4_RUNOUT], needs={3: PINK})
        picture, _ = runout_picture(info, 1, "A1", extras, stock_for=lambda f: 2)
        slots = {(s["ams_id"], s["tray_id"]): s for u in picture["units"] for s in u["slots"]}
        assert slots[(0, 0)]["remaining_g"] == 420.0
        assert slots[(0, 3)]["incoming"]["stock_count"] == 2


class TestBuildTodo:
    def test_the_paused_entry_carries_the_picture_and_its_filaments(self):
        info = _info([LITE_A4_RUNOUT], needs={3: PINK})
        body = build_todo([], {1: "A1 rechts"}, {}, [], {}, [], paused={1: info})
        paused = body["groups"][0]["entries"][0]["paused"]
        assert paused["cause"] == "runout_ams"
        assert paused["ams_picture"]["printer_name"] == "A1 rechts"
        assert paused["filaments"][0]["type"] == "PLA"
        assert paused["filaments"][0]["color"] == "#F5A9B8"
        # The response model takes the new state and fields.
        QueueTodoResponse.model_validate(body)

    def test_a_plain_pause_has_no_picture(self):
        body = build_todo([], {1: "A1"}, {}, [], {}, [], paused={1: PausedInfo("x", 1, 1, PauseCause())})
        paused = body["groups"][0]["entries"][0]["paused"]
        assert paused["ams_picture"] is None
        assert paused["filaments"] == []
        QueueTodoResponse.model_validate(body)


class TestRunningPrintNeeds:
    """Where the route reads what the paused print needs on each tray."""

    @staticmethod
    def _patch(monkeypatch, *, mapping, item=None, requirements=None, archive=None, file_filaments=None):
        from unittest.mock import AsyncMock

        import backend.app.main as main
        from backend.app.api.routes import print_queue
        from backend.app.services.print_scheduler import scheduler

        state = SimpleNamespace(print_ams_mapping=mapping, raw_data={}, gcode_file="", subtask_name="")
        monkeypatch.setattr(print_queue.printer_manager, "get_status", lambda pid: state)
        monkeypatch.setattr(scheduler, "_get_filament_requirements", AsyncMock(return_value=requirements))
        monkeypatch.setattr(main, "running_print_archive", AsyncMock(return_value=archive))
        monkeypatch.setattr(print_queue, "_file_filaments", lambda path, plate: file_filaments or [])
        return SimpleNamespace(scalar=AsyncMock(return_value=item))

    async def test_the_queue_jobs_filaments_with_its_overrides_on_the_mapped_trays(self, monkeypatch):
        from backend.app.api.routes.print_queue import _running_print_needs

        item = SimpleNamespace(
            id=7,
            ams_mapping=None,
            filament_overrides='[{"slot_id": 2, "type": "PETG", "color": "#112233", "color_name": "Navy"}]',
        )
        db = self._patch(
            monkeypatch,
            mapping=[0, 3],
            item=item,
            requirements=[
                {"slot_id": 1, "type": "PLA", "color": "#FFFFFF"},
                {"slot_id": 2, "type": "PLA", "color": "#F5A9B8", "tray_info_idx": "GFA00"},
            ],
        )
        needs = await _running_print_needs(db, 1)
        assert needs[0] == TodoFilament("PLA", "#FFFFFF")
        assert (needs[3].type, needs[3].color, needs[3].color_name) == ("PETG", "#112233", "Navy")

    async def test_a_print_the_queue_did_not_start_reads_its_archive(self, monkeypatch):
        from backend.app.api.routes.print_queue import _running_print_needs

        db = self._patch(
            monkeypatch,
            mapping=[-1, 254],
            archive=SimpleNamespace(file_path="archive/1/x.3mf"),
            file_filaments=[{"slot_id": 2, "type": "PLA", "color": "#F5A9B8"}],
        )
        assert await _running_print_needs(db, 1) == {254: TodoFilament("PLA", "#F5A9B8")}

    async def test_without_a_mapping_nothing_is_known(self, monkeypatch):
        from backend.app.api.routes.print_queue import _running_print_needs

        db = self._patch(monkeypatch, mapping=[], file_filaments=[{"slot_id": 1, "type": "PLA", "color": "#FFFFFF"}])
        assert await _running_print_needs(db, 1) == {}

    async def test_the_file_is_only_read_for_who_may_read_printers(self, monkeypatch):
        from backend.app.api.routes import print_queue

        called = []

        async def needs(db, printer_id):
            called.append(printer_id)
            return {3: PINK}

        monkeypatch.setattr(print_queue, "_running_print_needs", needs)
        info = _info([LITE_A4_RUNOUT])
        no_read = SimpleNamespace(has_permission=lambda perm: False)
        assert (await print_queue._with_running_needs(None, {1: info}, no_read))[1].needs == {}
        assert called == []
        out = await print_queue._with_running_needs(None, {1: info}, None)
        assert out[1].needs == {3: PINK}
