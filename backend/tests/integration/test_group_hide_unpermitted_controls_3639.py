"""The group option that hides the controls a group cannot use (#3639)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


def _auth(jwt: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {jwt}"}


async def _admin_token(async_client: AsyncClient) -> str:
    await async_client.post(
        "/api/v1/auth/setup",
        json={"auth_enabled": True, "admin_username": "hideadmin", "admin_password": "AdminPass1!"},
    )
    login = await async_client.post("/api/v1/auth/login", json={"username": "hideadmin", "password": "AdminPass1!"})
    assert login.status_code == 200, login.text
    return login.json()["access_token"]


async def _group(async_client: AsyncClient, admin: str, name: str, hide: bool) -> int:
    created = await async_client.post(
        "/api/v1/groups/",
        headers=_auth(admin),
        json={"name": name, "permissions": ["printers:read", "api_keys:create"], "hide_unpermitted_controls": hide},
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


async def _login(async_client: AsyncClient, admin: str, username: str, group_ids: list[int]) -> str:
    created = await async_client.post(
        "/api/v1/users/",
        headers=_auth(admin),
        json={"username": username, "password": "UserPass1!", "group_ids": group_ids},
    )
    assert created.status_code in (200, 201), created.text
    login = await async_client.post("/api/v1/auth/login", json={"username": username, "password": "UserPass1!"})
    return login.json()["access_token"]


async def _hides(async_client: AsyncClient, headers: dict[str, str]) -> bool:
    me = await async_client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200, me.text
    return me.json()["hide_unpermitted_controls"]


class TestGroupOption:
    async def test_off_on_a_new_group(self, async_client):
        admin = await _admin_token(async_client)
        created = await async_client.post("/api/v1/groups/", headers=_auth(admin), json={"name": "Plain"})
        assert created.status_code == 201, created.text
        assert created.json()["hide_unpermitted_controls"] is False

    async def test_round_trip(self, async_client):
        admin = await _admin_token(async_client)
        group_id = await _group(async_client, admin, "Helpers", True)

        fetched = await async_client.get(f"/api/v1/groups/{group_id}", headers=_auth(admin))
        assert fetched.json()["hide_unpermitted_controls"] is True

        off = await async_client.patch(
            f"/api/v1/groups/{group_id}", headers=_auth(admin), json={"hide_unpermitted_controls": False}
        )
        assert off.status_code == 200, off.text
        assert off.json()["hide_unpermitted_controls"] is False

    async def test_a_patch_without_the_field_keeps_it(self, async_client):
        admin = await _admin_token(async_client)
        group_id = await _group(async_client, admin, "Helpers", True)
        patched = await async_client.patch(
            f"/api/v1/groups/{group_id}", headers=_auth(admin), json={"description": "Farm helpers"}
        )
        assert patched.status_code == 200, patched.text
        assert patched.json()["hide_unpermitted_controls"] is True

    async def test_administrators_cannot_have_it(self, async_client):
        admin = await _admin_token(async_client)
        groups = (await async_client.get("/api/v1/groups/", headers=_auth(admin))).json()
        admins = next(g for g in groups if g["name"] == "Administrators")

        refused = await async_client.patch(
            f"/api/v1/groups/{admins['id']}", headers=_auth(admin), json={"hide_unpermitted_controls": True}
        )
        assert refused.status_code == 400, refused.text
        assert (await async_client.get(f"/api/v1/groups/{admins['id']}", headers=_auth(admin))).json()[
            "hide_unpermitted_controls"
        ] is False

    async def test_administrators_can_be_saved_with_it_off(self, async_client):
        # The edit form sends the whole group; an untouched option must not be refused.
        admin = await _admin_token(async_client)
        groups = (await async_client.get("/api/v1/groups/", headers=_auth(admin))).json()
        admins = next(g for g in groups if g["name"] == "Administrators")
        ok = await async_client.patch(
            f"/api/v1/groups/{admins['id']}", headers=_auth(admin), json={"hide_unpermitted_controls": False}
        )
        assert ok.status_code == 200, ok.text


class TestMeHideUnpermittedControls:
    async def test_admin_never_hides(self, async_client):
        admin = await _admin_token(async_client)
        assert await _hides(async_client, _auth(admin)) is False

    async def test_member_of_a_group_with_the_option(self, async_client):
        admin = await _admin_token(async_client)
        jwt = await _login(async_client, admin, "helper", [await _group(async_client, admin, "Helpers", True)])
        assert await _hides(async_client, _auth(jwt)) is True

    async def test_member_of_a_group_without_the_option(self, async_client):
        admin = await _admin_token(async_client)
        jwt = await _login(async_client, admin, "plain", [await _group(async_client, admin, "Plain", False)])
        assert await _hides(async_client, _auth(jwt)) is False

    async def test_all_groups_on_hides(self, async_client):
        admin = await _admin_token(async_client)
        ids = [await _group(async_client, admin, "One", True), await _group(async_client, admin, "Two", True)]
        jwt = await _login(async_client, admin, "both", ids)
        assert await _hides(async_client, _auth(jwt)) is True

    async def test_one_group_off_shows_everything(self, async_client):
        admin = await _admin_token(async_client)
        ids = [await _group(async_client, admin, "On", True), await _group(async_client, admin, "Off", False)]
        jwt = await _login(async_client, admin, "mixed", ids)
        assert await _hides(async_client, _auth(jwt)) is False

    async def test_a_user_without_groups_does_not_hide(self, async_client):
        admin = await _admin_token(async_client)
        jwt = await _login(async_client, admin, "nogroup", [])
        assert await _hides(async_client, _auth(jwt)) is False

    async def test_an_admin_in_a_group_with_the_option_does_not_hide(self, async_client):
        admin = await _admin_token(async_client)
        groups = (await async_client.get("/api/v1/groups/", headers=_auth(admin))).json()
        admins = next(g for g in groups if g["name"] == "Administrators")
        jwt = await _login(async_client, admin, "boss", [admins["id"], await _group(async_client, admin, "On", True)])
        assert await _hides(async_client, _auth(jwt)) is False

    async def test_an_api_key_never_hides(self, async_client):
        admin = await _admin_token(async_client)
        jwt = await _login(async_client, admin, "helper", [await _group(async_client, admin, "Helpers", True)])
        created = await async_client.post("/api/v1/api-keys/", headers=_auth(jwt), json={"name": "native"})
        assert created.status_code in (200, 201), created.text
        assert await _hides(async_client, {"X-API-Key": created.json()["key"]}) is False

    async def test_the_user_list_reports_it(self, async_client):
        admin = await _admin_token(async_client)
        await _login(async_client, admin, "helper", [await _group(async_client, admin, "Helpers", True)])
        users = (await async_client.get("/api/v1/users/", headers=_auth(admin))).json()
        by_name = {u["username"]: u for u in users}
        assert by_name["helper"]["hide_unpermitted_controls"] is True
        assert by_name["hideadmin"]["hide_unpermitted_controls"] is False

    async def test_the_server_still_enforces_permissions(self, async_client):
        admin = await _admin_token(async_client)
        jwt = await _login(async_client, admin, "helper", [await _group(async_client, admin, "Helpers", True)])
        denied = await async_client.get("/api/v1/users/", headers=_auth(jwt))
        assert denied.status_code == 403
