# Wiki draft – Feature A (#3576)

Repo: `maziggy/bambuddy-wiki` (mkdocs; admonitions `!!! note/tip/warning/info`, `:material-...:` icons in H2). Draft only; nothing is posted. Wiki clone checked: `/home/user/bambuddy-wiki` @ 330a416.

## Companion PR

- **Title:** `Files and jobs that clear their own plate (#3576)`
- **Description:** Companion to maziggy/bambuddy#___. Documents the **Clears plate automatically** flag on library files, print jobs and archives: where to set it (upload, file details, print dialog, queue bulk edit), how it interacts with **Require plate-clear confirmation** and the per-printer plate-clear choice, reprints, and the `clears_plate` API field. Touches `features/print-queue.md`, `features/file-manager.md` and `reference/api.md`.
- **Base:** `maziggy/bambuddy-wiki` default branch.

Notes:
- The wiki does not yet describe #3540's per-printer **Plate-clear confirmation** (*Use the global setting / Always require / Never require*). The text below names it. If the #3540 docs PR lands first, link to it; otherwise this PR covers it in one sentence.
- The wiki has no file-manager print dialog page of its own: "Starting a Print" in `features/file-manager.md` and "Print Options" in `features/print-queue.md` are the places for the dialog.
- The API reference has no library section, so library fields are noted in the queue section.

---

## 1. `docs/features/print-queue.md`

### 1a. Main section

Insert **after** the `#### Disabling Plate-Clear Confirmation` section (after its `!!! warning "Use With Caution"` block, before the `!!! tip "Permission Required"` block about the Clear Plate button; if that tip is part of the warning block, insert before `#### Watching the Gate From Outside Bambuddy`):

```markdown
#### Files and Jobs That Clear Their Own Plate

A file that ends with its own plate change or push-off does not need anyone to confirm the plate. Mark it as **Clears plate automatically** and the queue starts the next job right after a successful print, with the global **Require plate-clear confirmation** still on for everything else.

**What the flag means.** The file leaves the plate empty by itself, for example a plate changer or a push-off sequence at the end. Bambuddy does not look at the G-code: you say it, per file and per job.

**Where to set it**

| Where | How |
|-------|-----|
| Upload (also for a ZIP) | Tick **Files clear the plate automatically** in the upload dialog. It applies to every file of that upload |
| File details | Switch **Clears the plate automatically** in [File Manager](file-manager.md) → file details, then **Save** |
| Print dialog (per job) | Switch **Clears plate automatically** next to **Ask for Outcome**. It starts with the file's or the archive's value and you can change it for this job |
| Queue bulk edit | **Clears plate automatically**: Unchanged / Off / On |

Queued jobs with the flag show a **Clears plate** badge.

**When the queue skips the confirmation.** All of these must be true:

1. The print finished **successfully**
2. The job has the flag, and Bambuddy can positively tell that this finish is that queue job
3. The printer's **Plate-clear confirmation** is *Use the global setting*
4. **Require plate-clear confirmation** is on

| Printer's plate-clear setting | Global setting | Job flag | After a successful print |
|-------------------------------|:--------------:|:--------:|--------------------------|
| Use the global setting | On | On | **Next job starts, no confirmation** |
| Use the global setting | On | Off | Waits for **Clear Plate & Start Next** |
| Use the global setting | Off | any | Next job starts (the setting is off) |
| Always require | any | any | Waits for **Clear Plate & Start Next** |
| Never require | any | any | Next job starts, no confirmation |

A **failed or cancelled** print always keeps the confirmation, whatever the flag says, and **Require previous success** works as before. With the flag off everywhere, nothing changes.

**Reprints.** The flag is copied to the archive when the job starts, so a reprint from the archive, and a reprint through the webhook, starts with the same value. In the print dialog it shows the archive's value and you can change it.

**Which value a new job gets.** If the dialog or API call gives no value, the job takes the file's. For a job that may run on any printer of a model, it is on only if every alternative file has it. Without a file it takes the archive's, otherwise it is off. A dialog with several files leaves the choice to each file. The flag is copied when the job is created, so changing the file later does not change jobs already queued.

!!! warning "Printers without a plate changer"
    Anyone who may queue prints or edit files can set the flag. A printer without a plate changer must not start on an occupied plate, so set it to **Always require** in **Edit Printer → Plate-clear confirmation**. That setting wins over the flag. Jobs created from a pipeline or a virtual printer do not have the flag and still wait.

!!! note "Prints started outside Bambuddy"
    A print started on the printer or from a slicer has no queue job to carry the flag, so it behaves as before.
```

### 1b. Bulk edit table

In `## Bulk Editing` → `### Bulk Edit Modal`, insert this row **after** the **Require previous success** row:

```markdown
| **Clears plate automatically** | Toggle whether the jobs clear their own plate, so the queue does not wait for a plate confirmation after a successful print. See [Files and Jobs That Clear Their Own Plate](#files-and-jobs-that-clear-their-own-plate) |
```

### 1c. Print options table (optional)

In `### Print Options`, insert **after** the options table and before the `!!! info "Off / Auto / On"` block:

```markdown
The print dialog also has a **Clears plate automatically** switch next to **Ask for Outcome**. It is not a printer setting but tells the queue that the file clears its own plate; see [Files and Jobs That Clear Their Own Plate](#files-and-jobs-that-clear-their-own-plate).
```

## 2. `docs/features/file-manager.md`

### 2a. Upload

In `### Extraction Options`, insert **after** the options table and before `!!! tip "Combining Options"`:

```markdown
The upload dialog, for single files and for ZIPs, also has **Files clear the plate automatically**. Tick it only for sliced files that end with a plate change or push-off; it marks every file of the upload (see [Files and Jobs That Clear Their Own Plate](print-queue.md#files-and-jobs-that-clear-their-own-plate)).
```

### 2b. File details

Insert a new subsection **after** `### File Information` content (before `## :material-view-column: Column View`):

```markdown
### Clears the Plate Automatically

In the file details, **Clears the plate automatically** marks a file that ends with a plate change or push-off. After a successful print of such a file the queue starts the next job without waiting for a plate confirmation, unless the printer is set to **Always require**. New print jobs from this file start with this setting. Changing it needs permission to edit library files; click **Save** to apply it.

Details and the interplay with the global setting: [Files and Jobs That Clear Their Own Plate](print-queue.md#files-and-jobs-that-clear-their-own-plate).
```

### 2c. Print dialog

In `### Starting a Print`, insert this bullet **after** the **Print options** bullet:

```markdown
   - **Clears plate automatically** - Starts with the file's setting. Switch it for this job if the file ends with a plate change or push-off; see [Files and Jobs That Clear Their Own Plate](print-queue.md#files-and-jobs-that-clear-their-own-plate). With several files selected, each file keeps its own setting
```

## 3. `docs/reference/api.md`

Insert in `## Print Queue`, **after** the `### Add to Queue` request example and before `### Remove from Queue`:

````markdown
#### Clearing the plate

A file or job can clear its own plate: after a successful print the queue does not wait for a plate confirmation. See [Files and Jobs That Clear Their Own Plate](../features/print-queue.md#files-and-jobs-that-clear-their-own-plate).

| Where | Field | Notes |
|-------|-------|-------|
| `POST /queue` | `clears_plate` (bool, optional) | Leave it out to take the library file's value; for a job that may run on any printer of a model, the value shared by all its alternatives; else the archive's; else `false`. An explicit value always wins |
| `PATCH /queue/{id}` and `PATCH /queue/bulk` | `clears_plate` (bool, optional) | Sets it for the job(s) |
| Queue item response | `clears_plate` (bool) | |
| `GET /library/files`, `GET /library/files/{id}` | `clears_plate` (bool) | |
| `PUT /library/files/{id}` | `clears_plate` (bool, optional) | |
| `POST /library/files` and the ZIP extract | `clears_plate=true` (query parameter) | Marks every uploaded file. Default `false` |
| Archive response | `clears_plate` (bool) | Copied from the job when it starts, so a reprint inherits it |

The queue skips the plate confirmation only for a `completed` print of a flagged job on a printer whose plate-clear setting follows the global **Require plate-clear confirmation**. A printer set to *Always require* still waits, and failed or cancelled prints are unchanged.
````
