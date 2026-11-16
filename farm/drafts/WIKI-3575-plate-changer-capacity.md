# Wiki draft – Feature B (#3575)

Repo: `maziggy/bambuddy-wiki` (mkdocs; admonitions `!!! note/tip/warning/info`, event tables, `:material-...:` icons in H2). Draft only; nothing is posted.

## Companion PR

- **Title:** `Plate changer capacity per printer (#3575)`
- **Description:** Companion to maziggy/bambuddy#___. Documents the optional per-printer **Plate changer capacity**: the count on the printer card, **Refilled / Emptied**, what is counted, what the queue does at 0, the **Plate Changer Empty** notification and its `{capacity}` variable, and the API fields and endpoint. Touches `features/printer-control.md`, `features/print-queue.md`, `features/notifications.md` and `reference/api.md`.
- **Base:** `maziggy/bambuddy-wiki` default branch.

Note: the wiki does not yet describe #2860's per-printer **Plate-clear confirmation** (*Use the global setting / Always require / Never require*); it only knows the global switch. The text below mentions the per-printer choice by name. If the #3540 docs PR lands first, link to it; otherwise this PR covers it in one sentence.

---

## 1. `docs/features/printer-control.md`

Insert **after** the `### Clear Plate` section (after its "Permission Required" note, before `### Confirmation Modals`):

```markdown
### Plate Changer Capacity

A printer that clears its own plate (a plate changer or a push-off) can run the queue unattended, but a print started on an empty magazine or into a full bin can damage it. Give the printer a **capacity** and Bambuddy counts the plates for you.

**Setting it up**

1. Open **Edit Printer**
2. Enter **Plate changer capacity** (1-999), for example the number of plates in the magazine
3. Save. The changer is counted as full

Leave the field empty to turn counting off. Nothing is counted, blocked or notified then.

**On the printer card**

The card shows **Plates x / y**. The count is red with **Plate changer empty** at 0. **Refilled / Emptied** resets the count to the capacity after a confirmation. It works while the printer is offline or powered down.

**What uses a plate**

A print that finishes **successfully** and needs **no plate-clear confirmation** uses one plate. That means the printer is set to *Never require*, or it follows the global setting and **Require plate-clear confirmation** is off.

- Failed and cancelled prints do not count
- The printer's own calibration runs do not count
- Prints started on the printer itself or from a slicer **are** counted

**At 0**

The queue sends the printer nothing:

- A job pinned to this printer waits with **Plate changer empty: <printer>**
- A job for a printer model goes to another printer of that model
- Bambuddy does not wake the printer through its smart plug and does not keep its bed warm
- The check runs before the dispatch and again after the upload, right before the print starts

Press **Refilled / Emptied** after you have refilled the changer and emptied its bin, and the queue carries on. Drying is not affected.

!!! warning "Printers without a plate changer"
    Set printers that have no plate changer to **Always require** in **Edit Printer → Plate-clear confirmation**. Then they always wait for you to confirm the plate, whatever the global setting or a file says. Counting is only for printers that clear the plate themselves.

!!! warning "Known limits"
    - **Direct prints are not blocked.** A print started on the printer or from a slicer is counted but not stopped, the same as the plate-clear confirmation.
    - **A missed completion is not counted.** If Bambuddy is down when a print finishes, that plate is not counted. Press **Refilled / Emptied** when you refill the changer to resync.
    - **The plate-clear setting is read when the print finishes.** Changing it while a print runs applies to that print's count.
    - **A count that cannot be saved fails closed.** The printer is treated as empty until you reset it.

!!! note "Permissions"
    Setting the capacity needs permission to edit printers (`printers:update`). **Refilled / Emptied** needs the **Clear Plate** permission (`printers:clear_plate`).
```

## 2. `docs/features/print-queue.md`

Insert **after** the `#### Disabling Plate-Clear Confirmation` section (after its `!!! warning "Use With Caution"` block, before the next `!!! tip "Permission Required"`; if that tip belongs to the warning block, insert before the next `##`/`###` heading instead):

```markdown
#### Plate Changer Capacity

For printers that clear their own plate, set a **Plate changer capacity** in **Edit Printer**. The queue then counts one plate for each successful print that needed no confirmation, and at 0 it sends the printer nothing:

- A job pinned to the printer waits with **Plate changer empty: <printer>**
- A job for a printer model goes to another printer of that model

Press **Refilled / Emptied** on the printer card to continue. See [Plate Changer Capacity](printer-control.md#plate-changer-capacity) for what counts and the known limits.
```

## 3. `docs/features/notifications.md`

### 3a. Print Events table

Insert **after** the **Plate Clear Required** row:

```markdown
| **Plate Changer Empty** | A printer's plate changer used its last plate, so the queue sends it nothing until someone presses **Refilled / Emptied** on the printer card. **On by default.** It only fires for printers that have a [plate changer capacity](printer-control.md#plate-changer-capacity), so providers hear nothing new until you set one. |
```

### 3b. Variables

Insert **after** the `**Outcome Confirmation:**` list and before `**Common:**`:

```markdown
**Plate Changer Empty:**

- `{printer}` - Printer name
- `{capacity}` - The printer's plate changer capacity
```

Default template, for reference:

```text
Title: Plate Changer Empty
Body:  {printer}: all {capacity} plates used. Refill the plate changer and empty its bin, then press Refilled / Emptied on the printer card. The queue sends this printer nothing until then.
```

## 4. `docs/reference/api.md`

### 4a. Printer fields

Insert **after** the paragraph about `awaiting_plate_clear` (the one ending "…does not depend on the printer still being powered on."):

```markdown
`plate_capacity` and `plates_remaining` count the plates of a plate changer. Both are `null` when the printer has no capacity set. `plate_capacity` is 1-999 and can be set with the printer update; `plates_remaining` goes down by one for each successful print that needed no plate-clear confirmation. At `0` the queue sends the printer nothing. Setting `plate_capacity` starts the count full, lowering it clamps the count, and `null` turns counting off. `plates_remaining` can be sent too (0 up to the capacity, otherwise `422`). Changes are pushed as the `printer_plates_changed` [WebSocket](../features/monitoring.md) message with `plates_remaining` and `plate_capacity`. See [Plate Changer Capacity](../features/printer-control.md#plate-changer-capacity).
```

### 4b. Endpoint

Insert **after** the `### Clear Plate` section (after its `**Permission:** \`printers:clear_plate\`` line), before `### Set Print Speed`:

````markdown
### Refill Plates

```http
POST /printers/{id}/refill-plates
```

Reset the plate changer count after the changer was refilled and its bin emptied. Sets `plates_remaining` to `plate_capacity` and returns the updated printer. It only changes Bambuddy-side state, so the printer does not have to be online, and it does not touch `awaiting_plate_clear`.

**Errors:**

- `404` - Printer not found
- `400` - The printer has no plate changer capacity set

**Permission:** `printers:clear_plate`
````
