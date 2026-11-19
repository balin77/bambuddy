"""Finer printer permissions (#3248).

``printers:control`` is split into task-shaped permissions. An action is
allowed with its own permission OR the umbrella ``printers:control``, so every
group and API key that holds ``printers:control`` keeps all of it (no group row
is migrated). Printer scope still applies on top.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from backend.app.core.permissions import PERMISSION_UMBRELLAS, Permission

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

# permission -> [(method, path template)]. {p} is the printer id.
ROUTES: dict[str, list[tuple[str, str]]] = {
    "printers:pause_resume": [("POST", "/printers/{p}/print/pause"), ("POST", "/printers/{p}/print/resume")],
    "printers:stop": [("POST", "/printers/{p}/print/stop"), ("POST", "/printers/{p}/print/skip-objects")],
    "printers:filament": [
        ("POST", "/printers/{p}/ams/load"),
        ("POST", "/printers/{p}/ams/unload"),
        ("POST", "/printers/{p}/slots/0/0/configure"),
        ("POST", "/printers/{p}/ams/0/tray/0/reset"),
    ],
    "printers:tune": [
        ("POST", "/printers/{p}/temperature/nozzle"),
        ("POST", "/printers/{p}/temperature/bed"),
        ("POST", "/printers/{p}/temperature/chamber"),
        ("POST", "/printers/{p}/fan-speed"),
        ("POST", "/printers/{p}/print-speed"),
        ("POST", "/printers/{p}/airduct-mode"),
        ("POST", "/printers/{p}/chamber-light"),
        ("POST", "/printers/{p}/panda-breath"),
    ],
    "printers:motion": [
        ("POST", "/printers/{p}/bed-jog"),
        ("POST", "/printers/{p}/xy-jog"),
        ("POST", "/printers/{p}/extruder-jog"),
        ("POST", "/printers/{p}/home-axes"),
        ("POST", "/printers/{p}/select-extruder"),
    ],
    "printers:drying": [
        ("POST", "/printers/{p}/drying/start"),
        ("POST", "/printers/{p}/drying/stop"),
        ("POST", "/scheduled-dryings"),
        ("DELETE", "/scheduled-dryings/999999"),
    ],
    "printers:maintenance": [
        ("POST", "/printers/{p}/calibration"),
        ("POST", "/printers/{p}/print-options"),
        ("POST", "/printers/{p}/hms/clear"),
        ("POST", "/printers/{p}/hms/execute-action"),
        ("POST", "/printers/{p}/ams-backup"),
    ],
    "printers:admin": [
        ("POST", "/printers/{p}/connect"),
        ("POST", "/printers/{p}/disconnect"),
        ("POST", "/printers/{p}/logging/enable"),
        ("POST", "/printers/{p}/logging/disable"),
        ("DELETE", "/printers/{p}/logging"),
    ],
}
# Routes whose body must be valid for the request to get past validation.
BODIES: dict[tuple[str, str], dict] = {
    ("POST", "/scheduled-dryings"): {"printer_id": "{p}", "temp": 55, "duration_hours": 4},
}
ALL_ROUTES = [(perm, m, path) for perm, items in ROUTES.items() for m, path in items]


def _auth(jwt: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {jwt}"}


async def _admin_token(async_client: AsyncClient) -> str:
    await async_client.post(
        "/api/v1/auth/setup",
        json={"auth_enabled": True, "admin_username": "fineadmin", "admin_password": "AdminPass1!"},
    )
    login = await async_client.post("/api/v1/auth/login", json={"username": "fineadmin", "password": "AdminPass1!"})
    assert login.status_code == 200, login.text
    return login.json()["access_token"]


async def _member(
    async_client: AsyncClient, admin: str, name: str, permissions: list[str], printer_ids: list[int] | None = None
) -> tuple[str, int]:
    body: dict = {"name": f"g_{name}", "permissions": permissions}
    if printer_ids is not None:
        body.update(restrict_printers=True, printer_ids=printer_ids)
    group = await async_client.post("/api/v1/groups/", headers=_auth(admin), json=body)
    assert group.status_code == 201, group.text
    created = await async_client.post(
        "/api/v1/users/",
        headers=_auth(admin),
        json={"username": name, "password": "UserPass1!", "group_ids": [group.json()["id"]]},
    )
    assert created.status_code in (200, 201), created.text
    login = await async_client.post("/api/v1/auth/login", json={"username": name, "password": "UserPass1!"})
    assert login.status_code == 200, login.text
    return login.json()["access_token"], created.json()["id"]


async def _call(async_client: AsyncClient, headers: dict[str, str], method: str, path: str, printer_id: int) -> int:
    # The printer manager is mocked so a permitted call never reaches hardware;
    # only the gate in front of the route is under test.
    body: dict = dict(BODIES.get((method, path), {}))
    if "printer_id" in body:
        body["printer_id"] = printer_id
    with patch("backend.app.api.routes.printers.printer_manager", MagicMock()):
        try:
            response = await async_client.request(
                method, f"/api/v1{path.format(p=printer_id)}", headers=headers, json=body
            )
        except Exception:
            # The route body ran and tripped over the mock: the gate let it through, but it is
            # not a success, so report it as a server error (never 401/403/404).
            return 500
    return response.status_code


class TestUmbrellaMapping:
    async def test_every_fine_permission_is_granted_by_control(self):
        fine = set(ROUTES)
        assert fine == set(PERMISSION_UMBRELLAS)
        assert set(PERMISSION_UMBRELLAS.values()) == {Permission.PRINTERS_CONTROL.value}


@pytest.mark.parametrize("perm", list(ROUTES))
async def test_only_the_own_permission_opens_its_routes(async_client, printer_factory, perm):
    printer = await printer_factory(name="P")
    admin = await _admin_token(async_client)
    jwt, _ = await _member(async_client, admin, "only", ["printers:read", perm])
    headers = _auth(jwt)

    for other, method, path in ALL_ROUTES:
        status = await _call(async_client, headers, method, path, printer.id)
        if other == perm:
            assert status not in (401, 403), f"{method} {path} with {perm}: {status}"
        else:
            assert status == 403, f"{method} {path} must stay closed for {perm}: {status}"


async def test_control_still_opens_every_route(async_client, printer_factory):
    printer = await printer_factory(name="P")
    admin = await _admin_token(async_client)
    jwt, _ = await _member(async_client, admin, "umbrella", ["printers:read", "printers:control"])
    for perm, method, path in ALL_ROUTES:
        status = await _call(async_client, _auth(jwt), method, path, printer.id)
        assert status not in (401, 403), f"{method} {path} ({perm}) closed for printers:control: {status}"


async def test_diagnostic_stays_on_printers_read(async_client, printer_factory):
    printer = await printer_factory(name="P")
    admin = await _admin_token(async_client)
    jwt, _ = await _member(async_client, admin, "diagreader", ["printers:read"])
    with patch("backend.app.api.routes.printers.run_connection_diagnostic", new=AsyncMock(return_value={"checks": []})):
        status = await _call(async_client, _auth(jwt), "GET", "/printers/{p}/diagnostic", printer.id)
    assert status not in (401, 403)


async def test_read_only_user_gets_403_everywhere(async_client, printer_factory):
    printer = await printer_factory(name="P")
    admin = await _admin_token(async_client)
    jwt, _ = await _member(async_client, admin, "reader", ["printers:read"])
    for perm, method, path in ALL_ROUTES:
        assert await _call(async_client, _auth(jwt), method, path, printer.id) == 403, f"{method} {path} ({perm})"


async def test_printer_scope_still_applies_to_a_fine_permission(async_client, printer_factory):
    allowed = await printer_factory(name="Allowed")
    hidden = await printer_factory(name="Hidden")
    admin = await _admin_token(async_client)
    jwt, _ = await _member(async_client, admin, "scoped", ["printers:read", "printers:pause_resume"], [allowed.id])
    assert await _call(async_client, _auth(jwt), "POST", "/printers/{p}/print/pause", hidden.id) == 404
    assert await _call(async_client, _auth(jwt), "POST", "/printers/{p}/print/pause", allowed.id) != 404


class TestApiKeys:
    async def test_key_of_a_control_owner_opens_fine_routes(self, async_client, printer_factory):
        printer = await printer_factory(name="P")
        admin = await _admin_token(async_client)
        jwt, _ = await _member(async_client, admin, "keyowner", ["printers:control", "api_keys:create"])
        created = await async_client.post(
            "/api/v1/api-keys/", headers=_auth(jwt), json={"name": "k", "can_control_printer": True}
        )
        assert created.status_code == 200, created.text
        headers = {"X-API-Key": created.json()["key"]}
        for _perm, method, path in ALL_ROUTES:
            status = await _call(async_client, headers, method, path, printer.id)
            assert status not in (401, 403), f"{method} {path}: {status}"

    async def test_key_cannot_outrank_an_owner_with_only_a_fine_permission(self, async_client, printer_factory):
        printer = await printer_factory(name="P")
        admin = await _admin_token(async_client)
        jwt, _ = await _member(
            async_client, admin, "fineowner", ["printers:read", "printers:pause_resume", "api_keys:create"]
        )
        created = await async_client.post(
            "/api/v1/api-keys/", headers=_auth(jwt), json={"name": "k", "can_control_printer": True}
        )
        assert created.status_code == 200, created.text
        headers = {"X-API-Key": created.json()["key"]}
        assert await _call(async_client, headers, "POST", "/printers/{p}/print/pause", printer.id) not in (401, 403)
        assert await _call(async_client, headers, "POST", "/printers/{p}/print/stop", printer.id) == 403
