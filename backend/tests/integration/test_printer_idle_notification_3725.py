"""The "Printer idle: waiting for filament" event: channel switch, default template, Discord embed (#3725)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from backend.app.models.notification_template import DEFAULT_TEMPLATES, NotificationTemplate
from backend.app.schemas.notification_template import EVENT_VARIABLES, SAMPLE_DATA
from backend.app.services.notification_content import FilamentNeed, IdleJob, NotificationFilament
from backend.app.services.notification_service import NotificationService

EVENT = "printer_idle_for_filament"
DEFAULT = next(t for t in DEFAULT_TEMPLATES if t["event_type"] == EVENT)
RED = NotificationFilament(type="PLA", color_hex="#C62828", color_name="Lava Red", slot="A3")
BEIGE = NotificationFilament(type="PLA", color_hex="#7D6556", color_name="Army Beige")
JOBS = [
    IdleJob("Lamp_Base.5x.P1S.3mf", (FilamentNeed(RED, have_grams=196, need_grams=505), FilamentNeed(BEIGE))),
    IdleJob("Coaster_4x_p1s", (FilamentNeed(RED, have_grams=196, need_grams=300),)),
]
WEBHOOK = {"webhook_url": "https://discord.com/api/webhooks/1/a"}


@pytest.fixture
def service():
    return NotificationService()


@pytest.fixture
def seed_template(db_session):
    async def _seed(**edits):
        data = {**DEFAULT, **edits}
        db_session.add(
            NotificationTemplate(
                event_type=EVENT,
                name=data["name"],
                title_template=data["title_template"],
                body_template=data["body_template"],
            )
        )
        await db_session.commit()

    return _seed


async def _fire(service, db, jobs=JOBS, *, printer_id=1, send="_get_client"):
    response = MagicMock(status_code=204)
    client = AsyncMock()
    client.post = AsyncMock(return_value=response)
    with patch.object(service, send, new_callable=AsyncMock, return_value=client):
        await service.on_printer_idle_for_filament(printer_id, "P1S right", jobs, db)
    return client


@pytest.mark.asyncio
@pytest.mark.integration
async def test_switch_is_on_by_default_and_saves(async_client: AsyncClient):
    data = {"name": "Idle", "provider_type": "ntfy", "config": {"server": "https://ntfy.sh", "topic": "t"}}
    created = await async_client.post("/api/v1/notifications/", json=data)
    assert created.status_code == 200
    assert created.json()["on_printer_idle_for_filament"] is True

    provider_id = created.json()["id"]
    updated = await async_client.patch(
        f"/api/v1/notifications/{provider_id}", json={"on_printer_idle_for_filament": False}
    )
    assert updated.json()["on_printer_idle_for_filament"] is False
    listed = await async_client.get("/api/v1/notifications/")
    assert next(p for p in listed.json() if p["id"] == provider_id)["on_printer_idle_for_filament"] is False

    off = await async_client.post("/api/v1/notifications/", json={**data, "on_printer_idle_for_filament": False})
    assert off.json()["on_printer_idle_for_filament"] is False


def test_template_has_variables_samples_and_the_issue_wording():
    assert DEFAULT["title_template"] == "Printer idle: waiting for filament"
    assert set(EVENT_VARIABLES[EVENT]) <= set(SAMPLE_DATA[EVENT])
    for name in ("printer", "job_count", "jobs_wait", "jobs", "load"):
        assert "{" + name + "}" in DEFAULT["body_template"] or name == "job_count"
        assert name in EVENT_VARIABLES[EVENT]


class TestDiscord:
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_fields_and_first_sentence_as_description(
        self, service, db_session, seed_template, notification_provider_factory
    ):
        await seed_template()
        await notification_provider_factory(provider_type="discord", config=WEBHOOK)

        client = await _fire(service, db_session)

        embed = client.post.await_args.kwargs["json"]["embeds"][0]
        assert embed["title"] == "Printer idle: waiting for filament"
        assert embed["description"] == "P1S right has nothing it can print. 2 jobs wait for filament."
        assert embed["fields"] == [
            {"name": "Printer", "value": "P1S right", "inline": False},
            {
                "name": "Load",
                "value": "\U0001f534 PLA Lava Red (A3 has 196 g, needs 505 g)\n\U0001f7e4 PLA Army Beige",
                "inline": False,
            },
            {"name": "Jobs", "value": "Lamp_Base.5x.P1S.3mf · Coaster_4x_p1s", "inline": False},
        ]

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_one_filament_colours_the_embed_several_keep_the_green(
        self, service, db_session, seed_template, notification_provider_factory
    ):
        await seed_template()
        await notification_provider_factory(provider_type="discord", config=WEBHOOK)

        one = await _fire(service, db_session, [IdleJob("Lamp", (FilamentNeed(RED),))])
        several = await _fire(service, db_session)

        assert one.post.await_args.kwargs["json"]["embeds"][0]["color"] == 0xC62828
        assert several.post.await_args.kwargs["json"]["embeds"][0]["color"] == 0x00AE42

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_an_edited_template_is_sent_as_before(
        self, service, db_session, seed_template, notification_provider_factory
    ):
        await seed_template(body_template="{printer} is stuck: {jobs}")
        await notification_provider_factory(provider_type="discord", config=WEBHOOK)

        client = await _fire(service, db_session)

        assert client.post.await_args.kwargs["json"] == {
            "embeds": [
                {
                    "title": "Printer idle: waiting for filament",
                    "description": "P1S right is stuck: Lamp_Base.5x.P1S.3mf · Coaster_4x_p1s",
                    "color": 0x00AE42,
                }
            ]
        }


class TestText:
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_other_channels_get_the_whole_message(
        self, service, db_session, seed_template, notification_provider_factory
    ):
        await seed_template()
        await notification_provider_factory(provider_type="ntfy")
        sent = {}

        async def capture(config, title, message, *args, **kwargs):
            sent.update(title=title, message=message)
            return True, "ok"

        with patch.object(service, "_send_ntfy", side_effect=capture):
            await service.on_printer_idle_for_filament(1, "P1S right", JOBS, db_session)

        assert sent["title"] == "Printer idle: waiting for filament"
        assert sent["message"] == (
            "P1S right has nothing it can print. 2 jobs wait for filament.\n"
            "\U0001f534 PLA Lava Red (A3 has 196 g, needs 505 g)\n\U0001f7e4 PLA Army Beige\n"
            "Jobs: Lamp_Base.5x.P1S.3mf · Coaster_4x_p1s"
        )

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_one_job_waits(self, service, db_session, seed_template, notification_provider_factory):
        await seed_template()
        await notification_provider_factory(provider_type="discord", config=WEBHOOK)

        client = await _fire(service, db_session, [IdleJob("Lamp", (FilamentNeed(BEIGE),))])

        description = client.post.await_args.kwargs["json"]["embeds"][0]["description"]
        assert description == "P1S right has nothing it can print. 1 job waits for filament."

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_a_channel_with_the_switch_off_gets_nothing(
        self, service, db_session, seed_template, notification_provider_factory
    ):
        await seed_template()
        await notification_provider_factory(provider_type="discord", config=WEBHOOK, on_printer_idle_for_filament=False)

        client = await _fire(service, db_session)

        client.post.assert_not_awaited()

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_a_long_job_list_is_counted(self, service, db_session, seed_template, notification_provider_factory):
        await seed_template()
        await notification_provider_factory(provider_type="discord", config=WEBHOOK)
        jobs = [IdleJob(f"Job {n}", (FilamentNeed(BEIGE),)) for n in range(11)]

        client = await _fire(service, db_session, jobs)

        embed = client.post.await_args.kwargs["json"]["embeds"][0]
        assert embed["description"].endswith("11 jobs wait for filament.")
        assert embed["fields"][-1]["value"].endswith("Job 7 · +3 more")
