"""Print anyway in the "To do" list is offered per printer, not per job over all printers.

An "Any <model>" job whose colour is loaded but too little on one printer and
not loaded at all on the others is held on several printers, not all of them
for a short spool. On the printer where every filament is loaded it can still
be started anyway: ``short_only_printer_ids`` names those printers per job.
"""

from backend.app.schemas.print_queue import QueueTodoResponse
from backend.app.services.queue_todo import FilamentHold, TodoFilament, TodoJob, build_todo

SHORT = TodoFilament("PLA", "#FF0000", "Lava Red", short=True, required_grams=300.0)
MISSING = TodoFilament("PLA", "#FF0000", "Lava Red")
OTHER_MISSING = TodoFilament("PETG", "#0000FF", "Blue")

PRINTERS = {1: "P1S left", 2: "P1S right"}


def _job(item_id=1, *, pinned=None, ids=(1, 2), manual_start=False, can_start=True, **fields):
    return TodoJob(
        item_id,
        f"job{item_id}",
        frozenset(ids),
        pinned,
        None if pinned else "p1s",
        None if pinned else "P1S",
        manual_start,
        can_start,
        **fields,
    )


def _load_entries(jobs, holds, printers=PRINTERS):
    body = build_todo(jobs, printers, holds, [], {}, [])
    return [e for g in body["groups"] for e in g["entries"] if e["kind"] == "load_filament"]


def _by_printers(entries):
    """{printer ids of the entry: its first job}"""
    return {tuple(p["id"] for p in e["printers"]): e["jobs"][0] for e in entries}


SHORT_LEFT_MISSING_RIGHT = {1: [FilamentHold(1, 1, "P1S", (SHORT,)), FilamentHold(1, 2, "P1S", (MISSING,))]}


def test_short_on_one_printer_and_missing_on_another_is_offered_on_the_short_one():
    jobs = _by_printers(_load_entries([_job()], SHORT_LEFT_MISSING_RIGHT))

    assert jobs[(1,)]["short_only_printer_ids"] == [1]
    assert jobs[(1,)]["can_start"] is True
    # Over all its printers the job is not held only by short spools.
    assert jobs[(1,)]["short_only"] is False


def test_the_printer_that_lacks_the_filament_is_not_offered():
    jobs = _by_printers(_load_entries([_job()], SHORT_LEFT_MISSING_RIGHT))

    assert jobs[(2,)]["short_only_printer_ids"] == []
    assert jobs[(2,)]["can_start"] is False


def test_a_missing_filament_next_to_a_short_one_on_the_printer_is_not_offered():
    holds = {
        1: [FilamentHold(1, 1, "P1S", (SHORT, OTHER_MISSING)), FilamentHold(1, 2, "P1S", (MISSING, OTHER_MISSING))]
    }

    entries = _load_entries([_job()], holds)

    assert [j["short_only_printer_ids"] for e in entries for j in e["jobs"]] == [[], []]


def test_every_printer_short_names_each_of_them():
    holds = {1: [FilamentHold(1, 1, "P1S", (SHORT,)), FilamentHold(1, 2, "P1S", (SHORT,))]}

    (entry,) = _load_entries([_job()], holds)

    assert entry["jobs"] == [
        {"id": 1, "name": "job1", "can_start": True, "short_only": True, "short_only_printer_ids": [1, 2]}
    ]


def test_a_pinned_job_names_its_printer_as_before():
    short = _load_entries([_job(pinned=1, ids=(1,))], {1: [FilamentHold(1, 1, None, (SHORT,))]})
    missing = _load_entries([_job(pinned=1, ids=(1,))], {1: [FilamentHold(1, 1, None, (MISSING,))]})

    assert short[0]["jobs"] == [
        {"id": 1, "name": "job1", "can_start": True, "short_only": True, "short_only_printer_ids": [1]}
    ]
    assert missing[0]["jobs"] == [
        {"id": 1, "name": "job1", "can_start": False, "short_only": False, "short_only_printer_ids": []}
    ]


def test_a_staged_job_keeps_its_own_start():
    body = build_todo([_job(manual_start=True)], PRINTERS, SHORT_LEFT_MISSING_RIGHT, [], {}, [])
    entries = [e for g in body["groups"] for e in g["entries"]]

    load = [j for e in entries if e["kind"] == "load_filament" for j in e["jobs"]]
    staged = [j for e in entries if e["kind"] == "start_staged" for j in e["jobs"]]
    assert [(j["short_only_printer_ids"], j["can_start"]) for j in load] == [([], False), ([], False)]
    assert [(j["short_only_printer_ids"], j["can_start"]) for j in staged] == [([], True)]


def test_the_caller_who_may_not_start_the_job_gets_no_start():
    jobs = _by_printers(_load_entries([_job(can_start=False)], SHORT_LEFT_MISSING_RIGHT))

    assert jobs[(1,)]["short_only_printer_ids"] == [1]
    assert jobs[(1,)]["can_start"] is False


def test_a_printer_the_job_may_not_go_to_is_not_offered():
    # The hold names printer 1, which the job's creator (or the caller) may not use.
    jobs = _by_printers(_load_entries([_job(ids=(2,))], SHORT_LEFT_MISSING_RIGHT))

    assert jobs[(1,)]["short_only_printer_ids"] == []
    assert jobs[(1,)]["can_start"] is False


def test_a_printer_the_caller_does_not_see_has_no_entry():
    entries = _load_entries([_job(ids=(2,))], SHORT_LEFT_MISSING_RIGHT, printers={2: "P1S right"})

    assert [[p["id"] for p in e["printers"]] for e in entries] == [[2]]
    assert entries[0]["jobs"][0]["short_only_printer_ids"] == []


def test_a_job_with_printer_alternatives_is_not_offered_a_printer():
    # Its printer is chosen with its file at dispatch: it cannot be bound to one here.
    jobs = _by_printers(_load_entries([_job(pinnable=False)], SHORT_LEFT_MISSING_RIGHT))

    assert jobs[(1,)]["short_only_printer_ids"] == []
    assert jobs[(1,)]["can_start"] is False


def test_each_job_of_an_entry_is_judged_by_itself():
    holds = {
        1: [FilamentHold(1, 1, "P1S", (SHORT,)), FilamentHold(1, 2, "P1S", (MISSING,))],
        2: [FilamentHold(2, 1, "P1S", (SHORT,)), FilamentHold(2, 2, "P1S", (MISSING,))],
    }

    entries = _load_entries([_job(1), _job(2, can_start=False)], holds)

    short_entry = next(e for e in entries if [p["id"] for p in e["printers"]] == [1])
    assert [(j["id"], j["short_only_printer_ids"], j["can_start"]) for j in short_entry["jobs"]] == [
        (1, [1], True),
        (2, [1], False),
    ]


def test_the_response_schema_carries_the_printers():
    body = build_todo([_job()], PRINTERS, SHORT_LEFT_MISSING_RIGHT, [], {}, [])

    parsed = QueueTodoResponse.model_validate(body).model_dump()

    jobs = [j for g in parsed["groups"] for e in g["entries"] for j in e["jobs"]]
    assert sorted(j["short_only_printer_ids"] for j in jobs) == [[], [1]]
