# PR draft – Feature B (#3575)

- **Base:** `maziggy/bambuddy:dev`
- **Head:** `balin77:feature/plate-changer-capacity`
- **Title:** `Printers: a plate changer's plates are counted per printer (#3575)`
- **Status:** Draft – submit only after #3575 is assigned to balin77, #3540 is merged into dev and the branch is rebased so #3540's commit drops out, and the user approves.

---

## Description

A printer that clears its own plate (a plate changer, a push-off) lets the queue run unattended. Bambuddy does not know how many plates are left in the magazine or how much room is left in the bin, and a print started on an empty magazine or into a full bin can damage the printer. This PR adds an optional, per-printer **Plate changer capacity** and counts the plates down.

**Behaviour**

- **Setting it up.** Edit Printer has **Plate changer capacity** (1-999). Empty turns counting off. Setting it marks the changer as full (`plates_remaining = capacity`).
- **What counts.** A print that finishes **successfully** and needs **no plate-clear confirmation** uses one plate. That is: the printer is on *Never require* (#3540), or it follows the global setting and **Require plate-clear confirmation** is off. Failed and cancelled prints do not count. The printer's own calibration runs do not count. Prints started outside Bambuddy (printer screen, slicer) **are** counted, but never blocked.
- **At 0 the queue sends the printer nothing.** A job pinned to that printer waits with "Plate changer empty: <name>". A job for a printer model takes another printer of that model. There is no smart-plug wake and no keep-warm for an empty printer. The check runs before dispatch and again after the upload, right before the print starts.
- **Fail-closed.** If a count cannot be saved, or the capacity is set while the remaining count is unknown, the printer is treated as empty until someone resets it.
- **Refill.** The printer card shows "Plates x / y" and a **Refilled / Emptied** button. After a confirmation it resets the count to the capacity.
- **Notification.** New event **Plate Changer Empty**, sent when the last plate is used. It is on by default for every provider, but it only fires for printers that have a capacity, so existing installs hear nothing new.
- **API.** `plate_capacity` and `plates_remaining` on the printer (read and update) and `POST /printers/{id}/refill-plates`.
- **Feature off = no change.** Without a capacity nothing is counted, blocked or notified.
- **Permissions are reused.** `printers:update` sets the capacity, `printers:clear_plate` resets the count. No new permission.

Depends on #3540 (per-printer plate-clear override). The "auto-cleared finish" rule reads the #3540 override.

## Related Issue

Fixes #3575

Depends on #3540. This branch contains #3540's commit until it is merged into `dev`. After that the branch is rebased and the commit drops out of the diff.

## Documentation

**Companion docs PRs**:
- Wiki: maziggy/bambuddy-wiki#___

**Pick one**:
- [x] Docs PR(s) linked above
- [ ] No docs update required — reason: ___

## Type of Change

- [ ] Bug fix (non-breaking change that fixes an issue)
- [x] New feature (non-breaking change that adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to change)
- [ ] Documentation update
- [ ] Code refactoring
- [ ] Performance improvement
- [ ] Test addition or update

## Changes Made

**Model, migration, schemas, API**
- `printers.plate_capacity` and `printers.plates_remaining` (both INTEGER, nullable). Additive migrations in `database.py`; NULL capacity means counting is off.
- `notification_providers.on_plate_changer_empty` (BOOLEAN, default TRUE) with its migration.
- `PrinterUpdate`: `plate_capacity` 1-999, `plates_remaining` 0-999, 422 when remaining > capacity. `PrinterResponse` has both fields.
- `update_printer`: turning the capacity on starts full, changing it clamps the remaining count, turning it off clears it.
- `POST /printers/{id}/refill-plates` (permission `printers:clear_plate`): 404 for an unknown printer, 400 when the printer has no capacity, otherwise resets the count to the capacity. Does not touch `awaiting_plate_clear`.
- WebSocket event `printer_plates_changed` (`plates_remaining`, `plate_capacity`) so open pages update.

**Counting (`services/plate_changer.py`, `main.py`)**
- `consume_auto_cleared_plate()` runs in `on_print_complete` for a `completed` finish, before the queue row leaves "printing", so no queue pass can dispatch on the old count. One atomic conditional `UPDATE ... WHERE plates_remaining > 0 ... RETURNING`, no read-modify-write.
- Calibration runs are skipped. Any failure is logged and fails closed.

**Scheduler (`print_scheduler.py`)**
- `finish_needs_plate_confirmation()` and `load_plate_clear_policy()` are module helpers; #3540's `_plate_gate` now delegates to them (no behaviour change), so the counter and the gate use the same rule.
- Empty printers are loaded once per pass, after the busy-printers query. Pinned jobs wait with "Plate changer empty"; model jobs skip the printer (`_find_idle_printer_for_model`, `_wake_printer_for_model`); `_apply_keep_warm` ignores it; `_start_print` re-reads the count before and after the upload.

**Notifications**
- Event `plate_changer_empty` ("Plate Changer Empty") with a default template. Variables: `{printer}`, `{capacity}`, `{timestamp}`, `{app_name}`. Provider toggle and badge in the notification modal and card.

**Frontend**
- Edit Printer: capacity field. Printer card (compact and expanded, also on a powered-down printer): count pill, red at 0, **Refilled / Emptied** button with confirmation.
- 16 new i18n keys in all 16 locales, with real translations.

**Tests** — see Testing.

## Screenshots

<!-- to attach: from /home/user/plan/screens/ -->
- `r3-compact-1280.png` — printer card, compact view, desktop width
- `r3-compact-390.png` — printer card, compact view, phone width
- `r3-expanded-1280.png` — printer card, expanded view, desktop width
- `r3-expanded-390.png` — printer card, expanded view, phone width
- to attach (user): notification provider with the **Plate Changer Empty** toggle
- to attach (user): Edit Printer dialog with **Plate changer capacity**

## Testing

Backend (new test files, 111 test functions):
- `tests/unit/test_plate_changer_capacity_3575.py` — 29
- `tests/unit/test_printer_plate_changer_migration_3575.py` — 5
- `tests/integration/test_plate_changer_print_complete_3575.py` — 37
- `tests/integration/test_plate_changer_api_3575.py` — 29
- `tests/integration/test_plate_changer_notification_3575.py` — 11

Frontend (29 new tests):
- `PrinterPlateChanger.test.tsx` — 20
- `NotificationProviderCardPlateChanger.test.tsx` — 4
- `AddNotificationModal.test.tsx` — 4 added
- `useWebSocket.test.ts` — 1 added
- Existing fixtures updated for the new field.

Checks: `scripts/check_postgres_upgrade.py` passed. Ruff (lint + format), basedpyright, ESLint, `tsc`, knip, `npm run check:i18n` and Vitest are green.

- [x] I have tested this on my local machine
- [ ] I have tested with my printer model: <!-- TODO: user – printer model with plate changer, e.g. ... -->

Tested on printer: TODO user.

## Checklist

- [x] My code follows the project's coding style
- [x] I have commented my code where necessary
- [x] My changes generate no new warnings
- [x] I have tested my changes thoroughly

## Additional Notes

Known limits:
- **The policy is read at finish time.** Changing the printer's plate-clear setting while a print runs applies to that print's count.
- **A missed completion is not counted.** If Bambuddy is down when a print finishes, that plate is not counted. Press **Refilled / Emptied** when the magazine is refilled to resync.
- **Direct prints are not blocked.** Prints started on the printer or from a slicer are counted but not stopped, the same as the existing plate-clear gate.
- **A rare toast changed.** If the count reaches 0 between the upload and the start (a second print finishing in that window), the job stays in the queue. The user now sees "Plate changer empty, the job stays in the queue" instead of a generic failure toast.

I did not touch the wording of #3540. The helpers are extracted, not rewritten.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_0127bEAsde34UE3UDyMWQtka
