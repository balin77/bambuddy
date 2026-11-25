"""Print anyway on a chosen printer for an "Any <model>" job.

The "To do" list offers Print anyway under the printer whose spools are too
short. Start then takes that printer: the job is bound to it, as when the
scheduler assigns it, so it cannot go to a printer of the model that lacks the
filament. The confirmation names the short spools of that printer only.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from backend.app.models.library import LibraryFile
from backend.app.models.print_queue import PrintQueueVariant
from backend.app.services.print_scheduler import scheduler
from backend.app.services.queue_todo import FilamentHold, TodoFilament
from backend.tests.integration.test_printer_scope_1727 import _admin_token, _auth, _group, _user
from backend.tests.integration.test_queue_print_anyway_3659 import _deficit_on, _model_job, _patches

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

MISSING_WAIT = "Waiting for filament: P1S right (needs PLA (Red)) | P1S left (needs more filament)"
SHORT = TodoFilament("PLA", "#FF0000", "Red", short=True, required_grams=505.0)
MISSING = TodoFilament("PLA", "#FF0000", "Red")


@pytest.fixture
async def two_printers(printer_factory, archive_factory):
    left = await printer_factory(name="P1S left", model="P1S")
    right = await printer_factory(name="P1S right", model="P1S")
    archive = await archive_factory(left.id)
    return left, right, archive


@pytest.fixture
def holds():
    before = scheduler._filament_holds
    yield
    scheduler._filament_holds = before


async def _start(async_client, item_id: int, printer_id: int, skip: bool = False, headers=None):
    params: dict = {"printer_id": printer_id}
    if skip:
        params["skip_filament_check"] = "true"
    return await async_client.post(f"/api/v1/queue/{item_id}/start", params=params, headers=headers)


async def _add_alternative(db_session, item_id: int) -> None:
    file = LibraryFile(filename="p1s.3mf", file_path="/l/p1s.3mf", file_size=1, file_type="3mf")
    db_session.add(file)
    await db_session.flush()
    db_session.add(PrintQueueVariant(queue_item_id=item_id, position=0, library_file_id=file.id, target_model="P1S"))
    await db_session.commit()


async def _member(client: AsyncClient, printer_ids: list[int]) -> tuple[dict[str, str], int]:
    """A user who may read and start every job, limited to ``printer_ids``."""
    admin = await _admin_token(client)
    perms = await _group(client, admin, "start_perms", permissions=["queue:read_all", "queue:update_all"])
    team = await _group(client, admin, "start_team", printer_ids=printer_ids)
    token, user_id = await _user(client, admin, "start_member", [perms, team])
    return _auth(token), user_id


async def test_print_anyway_binds_the_job_to_the_chosen_printer(async_client, db_session, two_printers):
    left, _right, archive = two_printers
    item = await _model_job(db_session, archive.id, waiting_reason=MISSING_WAIT)

    response = await _start(async_client, item.id, left.id, skip=True)

    assert response.status_code == 200, response.text
    assert response.json()["printer_id"] == left.id
    await db_session.refresh(item)
    assert item.printer_id == left.id
    assert item.skip_filament_check is True
    # Bound the way the scheduler binds a model job: it keeps its model.
    assert item.target_model == "P1S"
    assert item.waiting_reason is None


async def test_the_confirmation_names_the_chosen_printer_only(async_client, db_session, two_printers):
    left, right, archive = two_printers
    # The reason names a printer that lacks the filament too: the chosen printer is asked whatever it says.
    item = await _model_job(db_session, archive.id, waiting_reason=MISSING_WAIT)
    p_deficit, p_mapping, p_types = _patches(_deficit_on({left.id, right.id}))

    with p_deficit, p_mapping, p_types:
        response = await _start(async_client, item.id, left.id)

    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "insufficient_filament"
    assert [d["printer_name"] for d in detail["deficit"]] == ["P1S left"]
    await db_session.refresh(item)
    assert item.printer_id is None
    assert item.skip_filament_check is False


async def test_a_spool_that_was_replaced_starts_on_the_chosen_printer_without_asking(
    async_client, db_session, two_printers
):
    left, right, archive = two_printers
    item = await _model_job(db_session, archive.id, waiting_reason=MISSING_WAIT)
    p_deficit, p_mapping, p_types = _patches(_deficit_on({right.id}))

    with p_deficit, p_mapping, p_types:
        response = await _start(async_client, item.id, left.id)

    assert response.status_code == 200, response.text
    await db_session.refresh(item)
    assert item.printer_id == left.id
    assert item.skip_filament_check is False


async def test_a_printer_of_another_model_is_refused(async_client, db_session, two_printers, printer_factory):
    _left, _right, archive = two_printers
    other = await printer_factory(name="X1C", model="X1C")
    item = await _model_job(db_session, archive.id)

    response = await _start(async_client, item.id, other.id, skip=True)

    assert response.status_code == 400, response.text
    await db_session.refresh(item)
    assert item.printer_id is None
    assert item.skip_filament_check is False


async def test_a_printer_at_another_location_is_refused(async_client, db_session, two_printers, printer_factory):
    _left, _right, archive = two_printers
    elsewhere = await printer_factory(name="P1S cellar", model="P1S", location="Cellar")
    item = await _model_job(db_session, archive.id, target_location="Workshop")

    response = await _start(async_client, item.id, elsewhere.id, skip=True)

    assert response.status_code == 400, response.text
    await db_session.refresh(item)
    assert item.printer_id is None


async def test_a_job_with_printer_alternatives_is_refused(async_client, db_session, two_printers):
    left, _right, archive = two_printers
    item = await _model_job(db_session, archive.id)
    await _add_alternative(db_session, item.id)

    response = await _start(async_client, item.id, left.id, skip=True)

    assert response.status_code == 400, response.text
    await db_session.refresh(item)
    assert item.printer_id is None


async def test_a_job_bound_to_a_printer_is_not_moved(async_client, db_session, two_printers):
    left, right, archive = two_printers
    item = await _model_job(db_session, archive.id, printer_id=left.id, target_model=None, manual_start=True)

    moved = await _start(async_client, item.id, right.id, skip=True)
    own = await _start(async_client, item.id, left.id, skip=True)

    assert moved.status_code == 400, moved.text
    assert own.status_code == 200, own.text
    await db_session.refresh(item)
    assert item.printer_id == left.id
    assert item.skip_filament_check is True


async def test_a_printer_outside_the_callers_scope_is_refused(async_client, db_session, two_printers):
    left, right, archive = two_printers
    item = await _model_job(db_session, archive.id)
    member, _ = await _member(async_client, [left.id])

    response = await _start(async_client, item.id, right.id, skip=True, headers=member)

    assert response.status_code == 404, response.text
    assert response.json()["detail"] == "Printer not found"
    await db_session.refresh(item)
    assert item.printer_id is None
    assert item.skip_filament_check is False


async def test_a_printer_outside_the_creators_scope_is_refused(async_client, db_session, two_printers):
    left, right, archive = two_printers
    _member_headers, member_id = await _member(async_client, [left.id])
    admin = _auth(await _admin_token(async_client))
    # The scheduler keeps a model job on its creator's printers: so does Start.
    item = await _model_job(db_session, archive.id, created_by_id=member_id)

    response = await _start(async_client, item.id, right.id, skip=True, headers=admin)

    assert response.status_code == 400, response.text
    await db_session.refresh(item)
    assert item.printer_id is None


async def test_the_list_offers_print_anyway_on_the_short_printer(async_client, db_session, two_printers, holds):
    left, right, archive = two_printers
    item = await _model_job(db_session, archive.id, waiting_reason=MISSING_WAIT)
    scheduler._filament_holds = {
        item.id: [FilamentHold(item.id, left.id, "P1S", (SHORT,)), FilamentHold(item.id, right.id, "P1S", (MISSING,))]
    }

    response = await async_client.get("/api/v1/queue/todo")

    assert response.status_code == 200, response.text
    entries = [e for g in response.json()["groups"] for e in g["entries"] if e["kind"] == "load_filament"]
    offered = {tuple(p["id"] for p in e["printers"]): e["jobs"][0] for e in entries}
    assert offered[(left.id,)]["short_only_printer_ids"] == [left.id]
    assert offered[(left.id,)]["can_start"] is True
    assert offered[(right.id,)]["short_only_printer_ids"] == []
    assert offered[(right.id,)]["can_start"] is False


async def test_the_list_offers_no_printer_outside_the_callers_scope(async_client, db_session, two_printers, holds):
    left, right, archive = two_printers
    item = await _model_job(db_session, archive.id)
    scheduler._filament_holds = {
        item.id: [FilamentHold(item.id, left.id, "P1S", (SHORT,)), FilamentHold(item.id, right.id, "P1S", (SHORT,))]
    }
    member, _ = await _member(async_client, [left.id])

    response = await async_client.get("/api/v1/queue/todo", headers=member)

    assert response.status_code == 200, response.text
    jobs = [j for g in response.json()["groups"] for e in g["entries"] for j in e["jobs"]]
    assert [j["short_only_printer_ids"] for j in jobs] == [[left.id]]
    assert "P1S right" not in response.text


async def test_the_list_offers_no_printer_for_a_job_with_alternatives(async_client, db_session, two_printers, holds):
    left, _right, archive = two_printers
    item = await _model_job(db_session, archive.id)
    await _add_alternative(db_session, item.id)
    scheduler._filament_holds = {item.id: [FilamentHold(item.id, left.id, "P1S", (SHORT,))]}

    response = await async_client.get("/api/v1/queue/todo")

    assert response.status_code == 200, response.text
    jobs = [j for g in response.json()["groups"] for e in g["entries"] for j in e["jobs"]]
    assert [j["short_only_printer_ids"] for j in jobs] == [[]]
