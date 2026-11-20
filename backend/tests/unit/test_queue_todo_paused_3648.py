"""The To do list shows a print that is paused and waits for a person (#3648)."""

from backend.app.services.queue_todo import (
    CAUSE_ERROR,
    CAUSE_PAUSED,
    CAUSE_RUNOUT_AMS,
    CAUSE_RUNOUT_EXTERNAL,
    KIND_PLATE_CLEAR,
    KIND_PRINT_PAUSED,
    PauseCause,
    PausedInfo,
    PausedSlot,
    PauseEpisodes,
    TodoJob,
    build_todo,
    pause_cause,
    paused_info_from_status,
    paused_slot,
)
from backend.app.utils.tray_ids import TrayLayout


def _job(job_id, printer_id, name="Job"):
    return TodoJob(job_id, name, frozenset({printer_id}), printer_id, None, None, False)


def _fault(attr, code, severity=2, description="Something", full_code="", actions=None):
    return {
        "attr": attr,
        "code": code,
        "severity": severity,
        "description": description,
        "full_code": full_code,
        "actions": actions or [],
    }


RUNOUT = _fault(0x07000000, "0x8011", description="AMS A filament ran out", full_code="0700000000018011")
EXTERNAL_RUNOUT = _fault(0x03000000, "0x8004", description="Filament ran out", full_code="03008004")
DOOR = _fault(0x05000100, "0x0006", severity=1, description="The door is open", full_code="0500010000010006")
HEATBED = _fault(0x05000200, "0x0007", severity=2, description="Heatbed temperature", full_code="0500020000020007")
NOTICE = _fault(0x05000300, "0x0008", severity=3, description="Just so you know")

A1 = PausedSlot(0, 0, False, False, 0, "PLA", "#FF0000")


def _build(jobs, paused, printers=None):
    return build_todo(jobs, printers or {1: "Alpha", 2: "Beta"}, {}, [], {}, [], paused)


class TestBuildTodo:
    def test_a_paused_printer_without_a_waiting_job_has_its_own_group_at_the_top(self):
        info = PausedInfo("Benchy", 42, 30, PauseCause())
        body = _build([_job(10, 1)], {2: info}, {1: "Alpha", 2: "Beta"})
        assert body["count"] == 1
        assert [g["printer_id"] for g in body["groups"]] == [2]
        entry = body["groups"][0]["entries"][0]
        assert entry["kind"] == KIND_PRINT_PAUSED
        assert entry["jobs"] == []
        assert entry["paused"]["job_name"] == "Benchy"

    def test_the_group_sorts_above_the_groups_that_wait_for_a_job(self):
        body = build_todo(
            [_job(10, 1)], {1: "Alpha", 2: "Beta"}, {}, [1], {}, [], {2: PausedInfo(None, None, None, PauseCause())}
        )
        assert [g["printer_id"] for g in body["groups"]] == [2, 1]

    def test_the_paused_entry_comes_first_in_a_group_with_waiting_jobs(self):
        jobs = [_job(10, 1, "Waiting")]
        body = build_todo(jobs, {1: "Alpha"}, {}, [1], {}, [], {1: PausedInfo("Benchy", 5, 9, PauseCause())})
        kinds = [e["kind"] for e in body["groups"][0]["entries"]]
        assert kinds == [KIND_PRINT_PAUSED, KIND_PLATE_CLEAR]
        assert body["count"] == 2
        paused = body["groups"][0]["entries"][0]
        assert [j["name"] for j in paused["jobs"]] == ["Waiting"]

    def test_a_paused_printer_outside_the_scope_is_left_out(self):
        body = _build([], {9: PausedInfo("Secret", 1, 1)}, {1: "Alpha"})
        assert body == {"count": 0, "groups": []}

    def test_without_paused_nothing_changes(self):
        assert build_todo([_job(10, 1)], {1: "Alpha"}, {}, [], {}, []) == {"count": 0, "groups": []}

    def test_the_record_is_carried_whole(self):
        cause = PauseCause(CAUSE_RUNOUT_AMS, ran_out=A1, expected=None, more_errors=2)
        body = _build([], {1: PausedInfo("Benchy", 42, 30, cause)})
        paused = body["groups"][0]["entries"][0]["paused"]
        assert paused == {
            "job_name": "Benchy",
            "progress": 42,
            "remaining_minutes": 30,
            "cause": "runout_ams",
            "ran_out": {
                "ams_id": 0,
                "tray_id": 0,
                "is_ht": False,
                "is_external": False,
                "ams_type": 0,
                "type": "PLA",
                "color": "#FF0000",
                "tray_info_idx": "",
                "tray_sub_brands": "",
            },
            "expected": None,
            "error": None,
            "more_errors": 2,
        }


class TestPauseCause:
    def test_no_faults_is_a_plain_pause(self):
        assert pause_cause([]).cause == CAUSE_PAUSED
        assert pause_cause([NOTICE]).cause == CAUSE_PAUSED

    def test_an_ams_runout_keeps_both_slots(self):
        expected = PausedSlot(0, 1, False, False, 0)
        cause = pause_cause([RUNOUT], expected=expected, ran_out=A1)
        assert (cause.cause, cause.ran_out, cause.expected) == (CAUSE_RUNOUT_AMS, A1, expected)

    def test_an_ams_runout_without_resolvable_slots(self):
        cause = pause_cause([RUNOUT])
        assert (cause.cause, cause.ran_out, cause.expected) == (CAUSE_RUNOUT_AMS, None, None)

    def test_the_placeholder_unit_counts_as_an_ams_runout(self):
        assert pause_cause([_fault(0x07FF0000, "0x8011")]).cause == CAUSE_RUNOUT_AMS

    def test_an_external_runout(self):
        cause = pause_cause([EXTERNAL_RUNOUT])
        assert cause.cause == CAUSE_RUNOUT_EXTERNAL
        assert cause.expected is None

    def test_a_runout_wins_over_an_error(self):
        cause = pause_cause([DOOR, RUNOUT])
        assert (cause.cause, cause.more_errors) == (CAUSE_RUNOUT_AMS, 1)

    def test_the_most_severe_error_is_named_and_the_others_counted(self):
        cause = pause_cause([HEATBED, DOOR, NOTICE])
        assert cause.cause == CAUSE_ERROR
        assert cause.error_description == "The door is open"
        assert cause.error_code == "0500-0100-0001-0006"
        assert cause.more_errors == 1

    def test_a_print_error_code_is_written_in_two_groups(self):
        fault = _fault(0x03000000, "0x4001", severity=1, description="Printing stopped", full_code="03004001")
        assert pause_cause([fault]).error_code == "0300-4001"

    def test_a_fault_without_text_or_action_is_no_reason(self):
        assert pause_cause([_fault(0x05000100, "0x0006", description=None)]).cause == CAUSE_PAUSED
        assert pause_cause([_fault(0x05000100, "0x0006", description=None, actions=["RESUME"])]).cause == CAUSE_ERROR


class TestPausedSlot:
    STATUS = {
        "ams": [
            {
                "id": 0,
                "ams_type": 0,
                "tray": [
                    {"id": 0, "tray_type": "PLA", "tray_color": "FF0000FF", "tray_info_idx": "GFA00"},
                    {"id": 1, "tray_type": "", "tray_color": "00000000"},
                ],
            },
            {"id": 128, "tray": [{"id": 0, "tray_type": "PETG", "tray_color": "00FF00FF"}]},
        ],
        "vt_tray": [{"id": 254, "tray_type": "TPU", "tray_color": "0000FFFF"}],
    }

    def _layout(self):
        return TrayLayout.from_units(self.STATUS["ams"], self.STATUS["vt_tray"])

    def test_a_loaded_slot_reports_its_filament(self):
        slot = paused_slot(self.STATUS, 0, self._layout())
        assert (slot.ams_id, slot.tray_id, slot.type, slot.color, slot.tray_info_idx) == (
            0,
            0,
            "PLA",
            "#FF0000",
            "GFA00",
        )
        assert (slot.is_ht, slot.is_external) == (False, False)

    def test_an_empty_slot_has_no_colour(self):
        slot = paused_slot(self.STATUS, 1, self._layout())
        assert (slot.type, slot.color) == ("", "")

    def test_an_ams_ht_and_the_external_spool(self):
        ht = paused_slot(self.STATUS, 128, self._layout())
        assert (ht.ams_id, ht.is_ht, ht.type) == (128, True, "PETG")
        ext = paused_slot(self.STATUS, 254, self._layout())
        assert (ext.is_external, ext.type) == (True, "TPU")

    def test_no_tray_is_no_slot(self):
        assert paused_slot(self.STATUS, None, self._layout()) is None


class TestPausedInfo:
    def test_fields_come_from_the_status(self):
        status = {
            "hms_errors": [RUNOUT],
            "expected_tray": 1,
            "previous_tray": 0,
            "progress": 42.0,
            "remaining_time": 90,
            **TestPausedSlot.STATUS,
        }
        info = paused_info_from_status(status, TrayLayout.from_units(status["ams"]), "Benchy")
        assert (info.job_name, info.progress, info.remaining_minutes) == ("Benchy", 42, 90)
        assert info.cause.cause == CAUSE_RUNOUT_AMS
        assert (info.cause.ran_out.type, info.cause.expected.tray_id) == ("PLA", 1)


class TestEpisodes:
    RUNOUT_CAUSE = PauseCause(CAUSE_RUNOUT_AMS, ran_out=A1)

    def test_rebuilt_empty_faults_keep_the_stored_cause(self):
        episodes = PauseEpisodes()
        episodes.resolve(1, "job-1", self.RUNOUT_CAUSE)
        assert episodes.resolve(1, "job-1", PauseCause()) is self.RUNOUT_CAUSE

    def test_another_job_is_another_episode(self):
        episodes = PauseEpisodes()
        episodes.resolve(1, "job-1", self.RUNOUT_CAUSE)
        assert episodes.resolve(1, "job-2", PauseCause()).cause == CAUSE_PAUSED

    def test_a_new_cause_replaces_the_stored_one(self):
        episodes = PauseEpisodes()
        episodes.resolve(1, "job-1", self.RUNOUT_CAUSE)
        error = PauseCause(CAUSE_ERROR, error_code="0300-4001")
        assert episodes.resolve(1, "job-1", error) is error
        assert episodes.resolve(1, "job-1", PauseCause()) is error

    def test_leaving_pause_clears_it(self):
        episodes = PauseEpisodes()
        episodes.resolve(1, "job-1", self.RUNOUT_CAUSE)
        episodes.prune(lambda pid: False)
        assert episodes.resolve(1, "job-1", PauseCause()).cause == CAUSE_PAUSED

    def test_another_printer_is_unaffected(self):
        episodes = PauseEpisodes()
        episodes.resolve(1, "job-1", self.RUNOUT_CAUSE)
        assert episodes.resolve(2, "job-1", PauseCause()).cause == CAUSE_PAUSED
