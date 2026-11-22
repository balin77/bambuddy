"""Which waiting jobs of the "To do" list can be started anyway (#3659).

A job that waits (not staged) only because spools are short is flagged
``short_only``; one that misses a filament altogether, or is staged, is not.
"""

from backend.app.services.queue_todo import FilamentHold, TodoFilament, TodoJob, build_todo

SHORT = TodoFilament("PLA", "#FF0000", "Lava Red", short=True, required_grams=300.0)
MISSING = TodoFilament("PLA", "#0000FF", "Blue")


def _job(item_id, *, pinned=1, manual_start=False, can_start=True):
    return TodoJob(
        item_id,
        f"job{item_id}",
        frozenset({1}),
        pinned,
        None if pinned else "p1s",
        None if pinned else "P1S",
        manual_start,
        can_start,
    )


def _job_dicts(jobs, holds):
    body = build_todo(jobs, {1: "Alpha"}, holds, [], {}, [])
    entries = [e for g in body["groups"] for e in g["entries"] if e["kind"] == "load_filament"]
    return [j for e in entries for j in e["jobs"]]


def test_a_job_held_only_by_a_short_spool_can_be_started_anyway():
    jobs = _job_dicts([_job(1)], {1: [FilamentHold(1, 1, None, (SHORT,))]})
    assert jobs == [{"id": 1, "name": "job1", "can_start": True, "short_only": True}]


def test_an_any_model_job_held_by_short_spools_can_be_started_anyway():
    jobs = _job_dicts([_job(1, pinned=None)], {1: [FilamentHold(1, 1, "P1S", (SHORT,))]})
    assert [(j["short_only"], j["can_start"]) for j in jobs] == [(True, True)]


def test_a_missing_filament_has_no_print_anyway():
    jobs = _job_dicts([_job(1)], {1: [FilamentHold(1, 1, None, (MISSING,))]})
    assert [(j["short_only"], j["can_start"]) for j in jobs] == [(False, False)]


def test_a_missing_filament_next_to_a_short_one_has_no_print_anyway():
    jobs = _job_dicts([_job(1)], {1: [FilamentHold(1, 1, None, (SHORT, MISSING))]})
    assert [j["short_only"] for j in jobs] == [False]


def test_the_caller_who_may_not_start_it_gets_no_start():
    jobs = _job_dicts([_job(1, can_start=False)], {1: [FilamentHold(1, 1, None, (SHORT,))]})
    assert [(j["short_only"], j["can_start"]) for j in jobs] == [(True, False)]


def test_a_staged_job_is_not_short_only():
    jobs = _job_dicts([_job(1, manual_start=True)], {1: [FilamentHold(1, 1, None, (SHORT,))]})
    assert [j["short_only"] for j in jobs] == [False]
