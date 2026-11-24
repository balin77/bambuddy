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
# Inside the same JSON: the short spools each job was told about (#3725).
SHORT_KEY = "short"

# A printer between two jobs of a queue is merely changing over: it must stand this long.
IDLE_WAIT = timedelta(minutes=5)

# The filaments the waiting jobs lack, as (type, colour): what makes it another message.
FilamentKey = frozenset[tuple[str, str]]


@dataclass
class WatchEntry:
    since: datetime
    announced: FilamentKey | None = None
    # In memory only: the printer was out of sight (off, or still connecting) in the last pass.
    unseen: bool = False


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class FilamentIdleWatch:
    """Per printer: since when it qualifies, and which filaments it was announced for."""

    def __init__(self, clock: Callable[[], datetime] = _utc_now) -> None:
        self.clock = clock
        self.entries: dict[int, WatchEntry] = {}
        # The short spools each job was told about: (job's slot, material), by queue item id.
        self.short: dict[int, set[tuple[int, str]]] = {}
        # What the settings table holds, to write only a change.
        self._saved: str = "{}"

    async def load(self, db: AsyncSession, printer_ids: Iterable[int] | None = None) -> None:
        """Read the saved state; what cannot be read is ignored.

        *printer_ids* are the printers that exist: the entry of a deleted one is dropped.
        """
        self.entries = {}
        self.short = {}
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
            for item_id, slots in (data.pop(SHORT_KEY, None) or {}).items():
                self.short[int(item_id)] = {(int(slot), str(kind)) for slot, kind in slots}
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
            self.short = {}

    def step(
        self,
        qualifying: dict[int, FilamentKey],
        keep: Iterable[int] = (),
        hold_back: Iterable[int] = (),
        frozen: Iterable[int] = (),
    ) -> list[int]:
        """One pass: *qualifying* printers with the filaments their jobs lack.

        The entry of every printer not qualifying goes, except those in *keep* (out of
        sight: off, or still connecting; the clock starts over when it is seen again
        unless it was announced) and those in *frozen* (held by a sensor or drying: neither
        a print nor an end of the wait). Returns the printers that are due a message, not
        those in *hold_back*. A message is due for a filament not announced yet; when the
        filaments only became fewer, that is remembered without one.
        """
        now = self.clock()
        keep = set(keep)
        frozen = set(frozen)
        for printer_id in [p for p in self.entries if p not in qualifying and p not in keep and p not in frozen]:
            del self.entries[printer_id]
        for printer_id in keep:
            if printer_id in self.entries:
                self.entries[printer_id].unseen = True
        held = set(hold_back)
        due = []
        for printer_id, key in qualifying.items():
            entry = self.entries.get(printer_id)
            if entry is None:
                entry = self.entries[printer_id] = WatchEntry(since=now)
            if entry.unseen:
                entry.unseen = False
                if entry.announced is None:
                    entry.since = now
            if entry.announced is not None and not key - entry.announced:
                entry.announced = key
            elif now - entry.since >= IDLE_WAIT and printer_id not in held:
                due.append(printer_id)
        return due

    def short_is_new(self, item_id: int, slots: set[tuple[int, str]]) -> bool:
        """Remember the short spools a job is told about; True when one of them was not told yet."""
        told = self.short.setdefault(item_id, set())
        if slots <= told:
            return False
        told |= slots
        return True

    def prune_short(self, item_ids: set[int]) -> None:
        self.short = {i: slots for i, slots in self.short.items() if i in item_ids}

    def announced(self, printer_id: int, key: FilamentKey) -> None:
        entry = self.entries.get(printer_id)
        if entry is not None:
            entry.announced = key

    def clear(self) -> None:
        self.entries = {}
        self.short = {}

    def _serialise(self) -> str:
        data: dict = {
            str(printer_id): {
                "since": entry.since.isoformat(),
                "announced": None if entry.announced is None else sorted([t, c] for t, c in entry.announced),
            }
            for printer_id, entry in sorted(self.entries.items())
        }
        if self.short:
            data[SHORT_KEY] = {str(i): sorted([slot, kind] for slot, kind in s) for i, s in sorted(self.short.items())}
        return json.dumps(data, sort_keys=True)

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
