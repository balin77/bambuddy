"""The "To do" list keeps a short spool's tray and the out-of-stock mark (#3615).

Farm takes only the tests of upstream's 874a703ad here; the earlier wait
reasons are covered by farm's own To do tests.
"""

from dataclasses import replace
from unittest.mock import MagicMock

from backend.app.services.print_scheduler import PrintScheduler
from backend.app.services.queue_todo import FilamentHold, ShortTray, TodoFilament, TodoJob, build_todo

RED = TodoFilament("PLA", "#FF0000", "Red")
SHORT_PLA = TodoFilament("PLA", "", short=True, short_trays=(ShortTray(0, 0, 40.0),), required_grams=120.0)


def _job(job_id: int, printer_ids: set[int], pinned: int | None, staged: bool = False) -> TodoJob:
    model = None if pinned is not None else "X1C"
    return TodoJob(job_id, f"Job {job_id}", frozenset(printer_ids), pinned, model and model.lower(), model, staged)


def _entries(todo: dict) -> list[dict]:
    return [entry for group in todo["groups"] for entry in group["entries"]]


class TestShortSpoolsKeepTheirTrays:
    """Equality of a ``TodoFilament`` ignores the short fields; the list must not."""

    A2 = replace(SHORT_PLA, short_trays=(ShortTray(0, 1, 12.0),), required_grams=30.0)
    A3 = replace(SHORT_PLA, short_trays=(ShortTray(0, 2, 20.0),), required_grams=50.0)

    def test_two_jobs_short_in_different_trays_are_two_entries(self):
        holds = {1: [FilamentHold(1, 7, None, (self.A2,))], 2: [FilamentHold(2, 7, None, (self.A3,))]}
        todo = build_todo([_job(1, {7}, 7), _job(2, {7}, 7)], {7: "A"}, holds, [], {}, [])

        named = [
            (e["jobs"][0]["id"], e["filaments"][0]["short_trays"][0]["tray_id"], e["filaments"][0]["required_grams"])
            for e in _entries(todo)
        ]
        assert named == [(1, 1, 30.0), (2, 2, 50.0)]

    def test_two_model_jobs_short_in_different_trays_of_one_printer_are_two_entries(self):
        holds = {1: [FilamentHold(1, 7, "X1C", (self.A2,))], 2: [FilamentHold(2, 7, "X1C", (self.A3,))]}
        todo = build_todo([_job(1, {7}, None), _job(2, {7}, None)], {7: "A"}, holds, [], {}, [])

        # Farm: an "Any <model>" entry names no tray (its printer's hint and
        # picture do), so the two entries are told apart by their jobs.
        assert [(e["jobs"][0]["id"], e["filaments"][0]["short_trays"]) for e in _entries(todo)] == [(1, []), (2, [])]

    def test_a_carried_hold_keeps_both_short_trays_and_a_missing_filament(self):
        scheduler = PrintScheduler()
        missing = TodoFilament("PLA", "")
        scheduler._filament_holds = {1: [FilamentHold(1, 7, None, (self.A2, self.A3, missing))]}
        scheduler._pass_holds = {}

        assert scheduler._carry_filament_hold(MagicMock(id=1, printer_id=7, target_model=None))
        (hold,) = scheduler._pass_holds[1]
        assert [(f.short, f.short_trays) for f in hold.filaments] == [
            (True, self.A2.short_trays),
            (True, self.A3.short_trays),
            (False, ()),
        ]


class TestOutOfStockHasItsOwnEntry:
    def test_a_filament_to_buy_and_the_same_one_to_load_are_two_entries(self):
        none_left = replace(RED, no_stock=True)
        for first, second in ((RED, none_left), (none_left, RED)):
            holds = {1: [FilamentHold(1, 7, None, (first,))], 2: [FilamentHold(2, 7, None, (second,))]}
            todo = build_todo([_job(1, {7}, 7), _job(2, {7}, 7)], {7: "A"}, holds, [], {}, [])

            marks = [(e["jobs"][0]["id"], e["filaments"][0]["no_stock"]) for e in _entries(todo)]
            assert marks == [(1, first.no_stock), (2, second.no_stock)]


class TestThePrinterModelNamesTheSlots:
    def test_a_printer_group_carries_its_model_and_a_model_group_its_target(self):
        holds = {1: [FilamentHold(1, 7, None, (SHORT_PLA,))], 2: [FilamentHold(2, 7, "X1C", (SHORT_PLA,))]}
        todo = build_todo([_job(1, {7}, 7), _job(2, {7}, None)], {7: "A"}, holds, [], {}, [], printer_models={7: "H2C"})

        assert [(g["printer_id"], g["printer_model"]) for g in todo["groups"]] == [(7, "H2C"), (None, "X1C")]
