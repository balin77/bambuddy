"""The farm-only notifications follow the readable format of #3641.

"Filament Out of Stock" (#3590) takes structured filaments, so its variables and
Discord fields work like those of the queue events; "Plate Changer Empty" (#3575)
gets Discord fields. Default template texts are unchanged; an edited template
keeps the old Discord payload.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.app.models.notification_template import DEFAULT_TEMPLATES, NotificationTemplate
from backend.app.services.notification_content import NotificationFilament
from backend.app.services.notification_service import NotificationService

LAVA_RED = NotificationFilament(type="PLA", color_hex="#C62828", color_name="Lava Red")
EARTH_BROWN = NotificationFilament(type="PLA", color_hex="#795548", color_name="Earth Brown")
ENTRIES = "PLA Lava Red, PLA Earth Brown"


@pytest.fixture
def service():
    return NotificationService()


@pytest.fixture
def seed_template(db_session):
    async def _seed(event_type, **edits):
        data = {**next(t for t in DEFAULT_TEMPLATES if t["event_type"] == event_type), **edits}
        db_session.add(
            NotificationTemplate(
                event_type=event_type,
                name=data["name"],
                title_template=data["title_template"],
                body_template=data["body_template"],
            )
        )
        await db_session.commit()

    return _seed


@pytest.fixture
def discord(notification_provider_factory):
    return lambda **kw: notification_provider_factory(
        provider_type="discord", config={"webhook_url": "https://discord.com/api/webhooks/1/a"}, **kw
    )


async def _sent(service, call):
    """Run ``call`` against a mocked HTTP client and return the embed Discord was sent."""
    client = AsyncMock()
    client.post = AsyncMock(return_value=MagicMock(status_code=204))
    with patch.object(service, "_get_client", new_callable=AsyncMock, return_value=client):
        await call()
    return client.post.await_args.kwargs["json"]["embeds"][0]


def _field_map(embed):
    return {f["name"]: f["value"] for f in embed.get("fields", [])}


class TestOutOfStock:
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_unchanged_template_gets_fields_and_the_filament_colour(
        self, service, db_session, seed_template, discord, printer_factory
    ):
        await seed_template("filament_out_of_stock")
        await discord(on_filament_out_of_stock=True)
        printer = await printer_factory(name="Sol P1s links", model="P1S")

        embed = await _sent(
            service,
            lambda: service.on_filament_out_of_stock(
                "Coaster_4x", "P1S", "PLA Lava Red", db_session, printer_id=printer.id, filaments=[LAVA_RED]
            ),
        )

        assert embed["title"] == "Filament Out of Stock"
        assert _field_map(embed) == {
            "Printer": "Sol P1s links",
            "Job": "Coaster_4x",
            "Out of stock": "\U0001f534 PLA Lava Red (#C62828)",
        }
        assert embed["color"] == 0xC62828

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_a_model_job_is_any_model_and_several_filaments_keep_the_green(
        self, service, db_session, seed_template, discord
    ):
        await seed_template("filament_out_of_stock")
        await discord(on_filament_out_of_stock=True)

        embed = await _sent(
            service,
            lambda: service.on_filament_out_of_stock(
                "Coaster_4x", "P1S", ENTRIES, db_session, filaments=[LAVA_RED, EARTH_BROWN]
            ),
        )

        fields = _field_map(embed)
        assert fields["Printer"] == "Any P1S"
        assert fields["Out of stock"] == "\U0001f534 PLA Lava Red (#C62828)\n\U0001f7e4 PLA Earth Brown (#795548)"
        assert embed["color"] == 0x00AE42

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_an_edited_template_gets_the_old_payload_and_the_new_variables(
        self, service, db_session, seed_template, discord
    ):
        await seed_template(
            "filament_out_of_stock", body_template="{job_name}: {color_emoji} {filament_type} {color_name} {color_hex}"
        )
        await discord(on_filament_out_of_stock=True)

        embed = await _sent(
            service,
            lambda: service.on_filament_out_of_stock(
                "Coaster_4x", "P1S", "PLA Lava Red", db_session, filaments=[LAVA_RED]
            ),
        )

        assert embed["description"] == "Coaster_4x: \U0001f534 PLA Lava Red #C62828"
        assert "fields" not in embed
        assert embed["color"] == 0x00AE42

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_the_default_text_keeps_the_plain_filament_text(self, service, db_session, seed_template, discord):
        await seed_template("filament_out_of_stock")
        await discord(on_filament_out_of_stock=True)

        embed = await _sent(
            service,
            lambda: service.on_filament_out_of_stock(
                "Coaster_4x", "P1S", "PLA Lava Red", db_session, filaments=[LAVA_RED]
            ),
        )

        assert embed["description"] == "Coaster_4x waits for PLA Lava Red, and none is left in the inventory."

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_without_structured_filaments_the_text_is_as_given(self, service, db_session, seed_template, discord):
        await seed_template("filament_out_of_stock")
        await discord(on_filament_out_of_stock=True)

        embed = await _sent(
            service,
            lambda: service.on_filament_out_of_stock("Benchy", "X1C", "PLA (Earth Brown)", db_session),
        )

        assert embed["description"] == "Benchy waits for PLA (Earth Brown), and none is left in the inventory."
        assert "Out of stock" not in _field_map(embed)

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_the_webhook_gets_the_variables(
        self, service, db_session, seed_template, notification_provider_factory
    ):
        await seed_template("filament_out_of_stock")
        await notification_provider_factory(
            provider_type="webhook",
            config={"webhook_url": "https://example.com/hook", "payload_format": "generic"},
            on_filament_out_of_stock=True,
        )
        client = AsyncMock()
        client.post = AsyncMock(return_value=MagicMock(status_code=200, text="ok"))
        with patch.object(service, "_get_client", new_callable=AsyncMock, return_value=client):
            await service.on_filament_out_of_stock(
                "Coaster_4x", "P1S", "PLA Lava Red", db_session, filaments=[LAVA_RED]
            )

        payload = client.post.await_args.kwargs["json"]
        assert payload["filament"] == "PLA Lava Red"
        assert payload["filament_type"] == "PLA"
        assert payload["color_name"] == "Lava Red"
        assert payload["color_hex"] == "#C62828"
        assert payload["color_emoji"] == "\U0001f534"


class TestPlateChangerEmpty:
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_unchanged_template_gets_printer_and_capacity_fields(
        self, service, db_session, seed_template, discord
    ):
        await seed_template("plate_changer_empty")
        await discord(on_plate_changer_empty=True)

        embed = await _sent(service, lambda: service.on_plate_changer_empty(7, "Sol P1s links", 10, db_session))

        assert embed["title"] == "Plate Changer Empty"
        assert embed["description"].startswith("Sol P1s links: all 10 plates used.")
        assert _field_map(embed) == {"Printer": "Sol P1s links", "Capacity": "10 plates"}
        assert embed["color"] == 0x00AE42

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_an_edited_template_gets_the_old_payload(self, service, db_session, seed_template, discord):
        await seed_template("plate_changer_empty", body_template="{printer} is out of plates ({capacity})")
        await discord(on_plate_changer_empty=True)

        embed = await _sent(service, lambda: service.on_plate_changer_empty(7, "Sol P1s links", 10, db_session))

        assert embed["description"] == "Sol P1s links is out of plates (10)"
        assert "fields" not in embed
