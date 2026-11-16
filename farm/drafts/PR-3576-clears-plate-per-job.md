# PR draft – Feature A (#3576)

- **Base:** `maziggy/bambuddy:dev`
- **Head:** `balin77:feature/clears-plate-per-job`
- **Title:** `Queue: a file or job can clear its own plate (#3576)`
- **Status:** Draft – submit only after #3576 is assigned to balin77, #3540 is merged into dev and the branch is rebased so #3540's commit drops out, and the user approves.
- **Interplay with #3575 (plate changer capacity):** both branches add `finish_needs_plate_confirmation()` / `load_plate_clear_policy()` to `print_scheduler.py` (identical except for this PR's `job_clears_plate` parameter). Whichever PR lands second rebases onto the other and keeps one copy of the helper. If #3575 lands first, this PR's `job_clears_plate` is added to it, and the plate-changer counting call in `on_print_complete` gets `job_clears_plate=` so a job that cleared its own plate counts one plate. If this PR lands first, #3575 adds that argument to the counting call.

---

## Description

The global **Require plate-clear confirmation** makes the queue wait after every print, and #3540 added a per-printer choice. Neither can tell a file that ends with its own plate change or push-off from one that leaves the part on the plate. On a farm with plate changers the queue stops after every job anyway; turning the setting off would let printers without a changer start on an occupied plate.

This PR lets a **file or a job** say "I clear my own plate". Library files, queue jobs and archives get a `clears_plate` flag (default off).

**Behaviour**

The queue skips the plate confirmation only when **all** of these are true. The finish is `completed`, the job has `clears_plate` set, the finish is positively matched to that queue job, the printer's plate-clear choice is *Use the global setting*, and **Require plate-clear confirmation** is on.

| Finish | Job flag | Printer setting | Global setting | Plate confirmation |
|--------|:--------:|-----------------|:--------------:|--------------------|
| completed | on | Use the global setting | on | **Not needed**, next job starts |
| completed | on | Always require | any | Needed (the printer wins) |
| completed | on | Never require | any | Not needed (as today) |
| completed | on | Use the global setting | off | Not needed (as today) |
| completed | off | Use the global setting | on | Needed (as today) |
| failed / cancelled / aborted | any | any | any | Unchanged: needed, `require_previous_success` applies |

Details:

- **Positive match.** The finishing job must be recognised as the queue job: exactly one `printing` row for the printer, the completion's print name echoes the job's, and a reconciled archive id, if there is one, equals the job's. Anything else (a second row, a name mismatch, an error while checking) keeps the confirmation. The check fails safe.
- **Lowers the gate.** A matched, flagged success on a printer that follows the global setting lowers the gate even if something else raised it during the same run, for example the printer's own calibration. The printer's own calibration runs do not raise it for a queue job any more either. Without that the flag would not work reliably on printers that calibrate.
- **Where to set it.** On upload (also for a ZIP), in the file details, per job in the print dialog (prefilled from the file, the archive or the job, and changeable), and in the queue's bulk edit. The queue shows a badge on these jobs.
- **Reprints.** At dispatch the job's value is copied to its archive, so a reprint from the archive inherits it. A webhook reprint inherits the archive's value.
- **Left out on create.** `clears_plate` is optional on `POST /queue/`: omitted means the library file's value, for a job that may run on any model the value shared by all its alternatives (`all()`), else the archive's, else `false`. An explicit value always wins. Multi-file print dialogs send no value, so each file keeps its own.
- **Feature off = no change.** The default is `false`. Nothing changes for files and jobs that do not set it, or when the global setting is off.

## Related Issue

Fixes #3576

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
- `library_files.clears_plate`, `print_queue.clears_plate`, `print_archives.clears_plate` (BOOLEAN NOT NULL DEFAULT FALSE). Additive migrations in `database.py`, matching the models; existing rows become `false`.
- Schemas: `clears_plate` on queue create (`bool | None`, `None` = fall back, see above), update and bulk update, queue/library/archive responses (`bool`, default `false`) and the library file update.
- Library: `POST /library/files` and the ZIP extract take `clears_plate=true` as a query parameter; `PUT /library/files/{id}` sets it; list and detail return it; add-to-queue copies it from the file.
- Queue create applies the fallback order; update and bulk update reuse the existing generic path. `services/print_batch.py` clones it with the other settings.
- Archives return it. A webhook reprint copies it from the archive.

**Scheduler and `main.py`**
- `finish_needs_plate_confirmation()` and `load_plate_clear_policy()` are module helpers in `print_scheduler.py`; #3540's `_plate_gate` now delegates to them (no behaviour change). The helper takes `job_clears_plate`.
- `on_print_complete` only raises the gate if the finish is not a matched, flagged success on a printer that follows the global setting. `_finishing_job_clears_plate()` (positive match, fail safe) and `_job_skips_plate_confirmation()` decide it, next to `_completion_belongs_to_queue_item`.
- At dispatch the job's value is copied to the archive (both dispatch sites, next to `confirm_requested`).

**Frontend**
- Print dialog: a **Clears plate automatically** pill next to **Ask for Outcome**. It shows the file's or archive's value until the job's value is decided, so it never contradicts what the backend applies. Detail queries refetch on mount. Multi-file and cross-model dialogs leave the value to the backend.
- File details: **Clears the plate automatically** toggle (disabled without edit permission). Upload modal: **Files clear the plate automatically** checkbox, also for ZIPs.
- Queue: a **Clears plate** badge and a tri-state in the bulk edit.
- 9 new i18n keys in all 16 locales, with real translations.

## Screenshots

<!-- to attach: from /home/user/plan/screens/ -->
- `a-printmodal-edit-1280.png` — print dialog (edit) with the **Clears plate automatically** pill
- `a-queue-1280.png` — queue with the **Clears plate** badge, desktop width
- `a-queue-390.png` — queue with the badge, phone width
- to attach (user): file details with the toggle
- to attach (user): upload modal with the checkbox
- to attach (user): bulk edit with the **Clears plate automatically** row

## Testing

Backend (new test files, 74 test functions):
- `tests/unit/test_clears_plate_gate_3576.py` — 7
- `tests/unit/test_clears_plate_migration_3576.py` — 5
- `tests/integration/test_clears_plate_print_complete_3576.py` — 26 (success / failed / cancelled / aborted, flagged or not, global on or off, printer inherit / on / off, name or archive-id mismatch, two printing rows, next job dispatched)
- `tests/integration/test_clears_plate_api_3576.py` — 36 (create fallback order, explicit `false`, update, bulk, batch clone, library upload / ZIP / update / list / detail, add-to-queue, archive and webhook inheritance, dispatch copies)

Frontend (30 new tests):
- `PrintModalClearsPlate.test.tsx` — 19
- `FileUploadModal.test.tsx` — 4 added
- `LibraryFileDetailsModal.test.tsx` — 3 added
- `QueuePage.test.tsx` — 4 added

Checks: `scripts/check_postgres_upgrade.py`, Ruff (lint + format), basedpyright, ESLint, `tsc`, knip, `npm run check:i18n` and Vitest are green. <!-- TODO: master – confirm final results before submitting -->

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
- **The flag is copied when the job is created.** Changing the file's flag later does not change jobs already in the queue. Edit the job or use the bulk edit.
- **Jobs that do not come from the dialog.** Webhook reprints take the archive's value. Pipeline and virtual-printer jobs keep the default `false`, so they still wait for a confirmation.
- **Only queue jobs count.** A print started on the printer or from a slicer has no job to carry the flag and behaves as before.
- **A missed completion is not special.** If the finish cannot be matched to its job, the confirmation is kept.

Why there is no G-code check: I did not try to guess from the G-code whether a file contains a plate change or push-off. Such a heuristic would be fragile and a wrong guess starts a print on an occupied plate. The user says it, explicitly, per file and per job.

**Security note.** Anyone who may create or edit queue jobs (`queue:create`, `queue:update`) or edit library files can set the flag. On a printer without a plate changer it would skip the confirmation that protects it. Set such printers to **Always require** (#3540): that setting wins over the flag.

I did not touch the wording of #3540. The helpers are extracted, not rewritten.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_0127bEAsde34UE3UDyMWQtka
