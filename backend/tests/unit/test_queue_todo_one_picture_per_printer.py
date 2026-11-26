"""A To do entry of an "Any <model>" job never carries two AMS pictures of one printer.

The farm state the multiplied picture was seen in: two A1, the left one idle
with every colour of the first job loaded but Cotton White too little, the
right one printing; three jobs for any A1. Whatever the scheduler's passes
left in the holds (a hold recorded again, the same list built again and
again), each entry has one picture per printer and names each job once.
"""

from backend.app.schemas.print_queue import QueueTodoResponse
from backend.app.services.queue_todo import (
    FilamentHold,
    PictureSlot,
    ShortTray,
    SlotExtra,
    SlotHint,
    TodoFilament,
    TodoJob,
    build_todo,
    one_per_printer,
    priority_state,
)

PRINTERS = {1: "A1 Links", 2: "A1 rechts"}
IDLE = {1}

BLACK = ("PLA", "#000000", "Charcoal Black")
BEIGE = ("PLA", "#B2A78E", "Army Beige")
WHITE = ("PLA", "#E6DDDB", "Cotton White")
RED = ("PLA", "#7B2D34", "Army Red")
MUTED_WHITE = ("PLA", "#F0F0E8", "Muted White")
GOLD = ("PLA", "#E4BD68", "Gold")
MUTED_RED = ("PLA", "#9B4A4A", "Muted Red")
ICE = ("PLA", "#A4D0DF", "Pastel Ice")


def _missing(*filaments, forced=True):
    return tuple(TodoFilament(*f, forced=forced) for f in filaments)


WHITE_SHORT = TodoFilament(*WHITE, short=True, short_trays=(ShortTray(0, 2, 0.0),), required_grams=21.0, forced=True)


def _slot(tray_id, filament):
    return PictureSlot(0, tray_id, tray_id, False, False, 2, None, filament[0], filament[1])


def _hint(printer_id, running=frozenset()):
    picture = tuple(_slot(i, f) for i, f in enumerate((BLACK, BEIGE, WHITE, RED)))
    external = PictureSlot(255, 0, 254, False, True, None, None, empty=True)
    return SlotHint(printer_id, "all_needed", picture=(*picture, external), running=running)


HINTS = {1: _hint(1), 2: _hint(2, running=frozenset({0, 1, 2, 3}))}
EXTRAS = {(1, 0, 2): SlotExtra(remaining_grams=0.0, color_name="Cotton White")}

JOBS = [
    TodoJob(92, "four_colours.3mf", frozenset(PRINTERS), None, "a1", "A1", False, True),
    TodoJob(87, "muted.3mf", frozenset(PRINTERS), None, "a1", "A1", False, True),
    TodoJob(91, "ice.3mf", frozenset(PRINTERS), None, "a1", "A1", False, True),
]

# What one scheduler pass records: a hold per printer that lacks something.
HOLDS = {
    92: [
        FilamentHold(92, 1, "A1", (WHITE_SHORT,)),
        FilamentHold(92, 2, "A1", _missing(BEIGE, RED, BLACK, WHITE)),
    ],
    87: [
        FilamentHold(87, 1, "A1", _missing(MUTED_WHITE, GOLD, MUTED_RED)),
        FilamentHold(87, 2, "A1", _missing(MUTED_WHITE, BLACK, GOLD, MUTED_RED)),
    ],
    91: [FilamentHold(91, 1, "A1", _missing(ICE, forced=False))],
}
PRIORITIES = {92: priority_state(False, 72), 87: priority_state(False, 56), 91: priority_state(False, 72)}


def _build(holds=HOLDS, jobs=JOBS):
    body = build_todo(
        jobs, PRINTERS, holds, [], {}, [], priorities=PRIORITIES, slot_hints=HINTS, slot_extras=EXTRAS,
        idle_printers=IDLE,
    )  # fmt: skip
    QueueTodoResponse.model_validate(body)
    return body


def _entries(body):
    return [e for g in body["groups"] for e in g["entries"]]


def _picture_printers(entry):
    return [p["printer_id"] for p in entry["ams_pictures"]]


def _assert_nothing_twice(body):
    for entry in _entries(body):
        for ids in (
            _picture_printers(entry),
            [p["id"] for p in entry["printers"]],
            [j["id"] for j in entry["jobs"]],
            [h["printer_id"] for h in entry["slot_hints"]],
        ):
            assert len(ids) == len(set(ids)), entry
        for job in entry["jobs"]:
            assert len(job["short_only_printer_ids"]) == len(set(job["short_only_printer_ids"]))
        for names in (entry["filaments"], *(p["filaments"] for p in entry["ams_pictures"])):
            keys = [(f["type"], f["color"], f["short"]) for f in names]
            assert len(keys) == len(set(keys)), entry


def test_the_farm_state_gives_three_entries_each_with_one_picture_per_printer():
    body = _build()

    assert body["count"] == 3
    (group,) = body["groups"]
    assert group["target_model"] == "A1"
    by_job = {e["jobs"][0]["id"]: e for e in group["entries"]}
    assert {job: _picture_printers(e) for job, e in by_job.items()} == {92: [1, 2], 87: [1, 2], 91: [1]}
    assert {job: [p["id"] for p in e["printers"]] for job, e in by_job.items()} == {92: [1], 87: [1], 91: [1]}
    _assert_nothing_twice(body)

    # Job 92 on the idle printer: Cotton White in A3 goes out, a new spool goes in.
    links, rechts = by_job[92]["ams_pictures"]
    assert [f["color_name"] for f in links["filaments"]] == ["Cotton White"]
    slots = {(s["ams_id"], s["tray_id"]): s for u in links["units"] for s in u["slots"]}
    assert slots[(0, 2)]["state"] == "out"
    assert slots[(0, 2)]["incoming"]["required_g"] == 21.0
    assert by_job[92]["jobs"][0]["short_only_printer_ids"] == [1]
    # The printing one misses all four and takes nothing while it prints.
    assert len(rechts["filaments"]) == 4
    assert rechts["unplaced"] == [0, 1, 2, 3]


def test_building_the_list_again_and_again_gives_the_same_list():
    first = _build()

    for _ in range(10):
        assert _build() == first


def test_holds_recorded_once_more_with_every_pass_add_no_picture():
    first = _build()

    for passes in range(2, 12):
        # Every hold of a job as often as passes ran, as if none replaced the earlier ones.
        repeated = {job_id: holds * passes for job_id, holds in HOLDS.items()}
        body = _build(repeated)
        _assert_nothing_twice(body)
        assert body == first


def test_jobs_that_wait_for_the_same_share_one_entry_with_one_picture_per_printer():
    twin = TodoJob(93, "four_colours_again.3mf", frozenset(PRINTERS), None, "a1", "A1", False, True)
    holds = {**HOLDS, 93: [FilamentHold(93, hold.printer_id, "A1", hold.filaments) for hold in HOLDS[92]]}

    body = _build(holds, [*JOBS, twin])

    assert body["count"] == 3
    shared = next(e for e in _entries(body) if len(e["jobs"]) == 2)
    assert [j["id"] for j in shared["jobs"]] == [92, 93]
    assert _picture_printers(shared) == [1, 2]
    _assert_nothing_twice(body)


def test_a_printer_named_again_among_the_candidates_is_kept_once_the_first_one():
    first = (1, "A1 Links", (WHITE_SHORT,))
    again = (1, "A1 Links", _missing(RED))
    other = (2, "A1 rechts", _missing(RED))

    assert one_per_printer([first, other, again, other, again]) == [first, other]
