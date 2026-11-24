"""When did a printer start standing idle because its waiting jobs lack filament (#3725).

The scheduler reports each pass which printers qualify: idle, with waiting jobs
none of which can start for want of filament. This keeps the clock per printer
and says when one has stood for five minutes and has not been announced yet. A
printer is announced once per standstill; again only after something else
happened in between (it printed, or stopped qualifying) or the filaments it
waits for changed.

The state is kept in the settings table, so a restart neither starts the five
minutes over nor repeats a message already sent. It is written when it changes,
never on every pass.
"""

import json
import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.db_dialect import upsert_setting
from backend.app.models.settings import Settings

logger = logging.getLogger(__name__)

SETTING_KEY = "queue_filament_idle_watch"

# A printer between two jobs of a queue is merely changing over: it must stand this long.
IDLE_WAIT = timedelta(minutes=5)

# The filaments the waiting jobs lack, as (type, colour): what makes it another message.
FilamentKey = frozenset[tuple[str, str]]


@dataclass
class WatchEntry:
    since: datetime
    announced: FilamentKey | None = None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class FilamentIdleWatch:
    """Per printer: since when it qualifies, and which filaments it was announced for."""

    def __init__(self, clock: Callable[[], datetime] = _utc_now) -> None:
        self.clock = clock
        self.entries: dict[int, WatchEntry] = {}
        # What the settings table holds, to write only a change.
        self._saved: str = "{}"

    async def load(self, db: AsyncSession, printer_ids: Iterable[int] | None = None) -> None:
        """Read the saved state; what cannot be read is ignored.

        *printer_ids* are the printers that exist: the entry of a deleted one is dropped.
        """
        self.entries = {}
        self._saved = "{}"
        try:
            raw = await db.scalar(select(Settings.value).where(Settings.key == SETTING_KEY))
        except Exception as e:
            logger.debug("Could not read the saved idle-for-filament state: %s", e)
            return
        if not raw:
            return
        self._saved = raw
        try:
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError("not an object")
            now = self.clock()
            known = set(printer_ids) if printer_ids is not None else None
            for key, value in data.items():
                printer_id = int(key)
                if known is not None and printer_id not in known:
                    continue
                since = datetime.fromisoformat(value["since"])
                if since.tzinfo is None:
                    since = since.replace(tzinfo=timezone.utc)
                announced = value.get("announced")
                self.entries[printer_id] = WatchEntry(
                    since=min(since, now),
                    announced=None if announced is None else frozenset((str(t), str(c)) for t, c in announced),
                )
        except Exception as e:
            logger.debug("Ignoring the saved idle-for-filament state, it cannot be read: %s", e)
            self.entries = {}

    def step(
        self, qualifying: dict[int, FilamentKey], keep: Iterable[int] = (), hold_back: Iterable[int] = ()
    ) -> list[int]:
        """One pass: *qualifying* printers with the filaments their jobs lack.

        The entry of every printer not qualifying goes, except those in *keep* (state not
        known right now, such as a printer still connecting). Returns the printers that
        are due a message, not those in *hold_back*.
        """
        now = self.clock()
        keep = set(keep)
        for printer_id in [p for p in self.entries if p not in qualifying and p not in keep]:
            del self.entries[printer_id]
        held = set(hold_back)
        due = []
        for printer_id, key in qualifying.items():
            entry = self.entries.get(printer_id)
            if entry is None:
                entry = self.entries[printer_id] = WatchEntry(since=now)
            if now - entry.since >= IDLE_WAIT and entry.announced != key and printer_id not in held:
                due.append(printer_id)
        return due

    def announced(self, printer_id: int, key: FilamentKey) -> None:
        entry = self.entries.get(printer_id)
        if entry is not None:
            entry.announced = key

    def clear(self) -> None:
        self.entries = {}

    def _serialise(self) -> str:
        return json.dumps(
            {
                str(printer_id): {
                    "since": entry.since.isoformat(),
                    "announced": None if entry.announced is None else sorted([t, c] for t, c in entry.announced),
                }
                for printer_id, entry in sorted(self.entries.items())
            },
            sort_keys=True,
        )

    async def save_if_changed(self, db: AsyncSession) -> None:
        text = self._serialise()
        if text == self._saved:
            return
        try:
            # A savepoint: a failed write must not leave the pass's session unusable.
            async with db.begin_nested():
                await upsert_setting(db, Settings, SETTING_KEY, text)
            await db.commit()
            self._saved = text
        except Exception as e:
            logger.debug("Could not save the idle-for-filament state: %s", e)
