# Issue drafts – notifications: readable layout, raw reason code, language

**Status:** All three posted on 20 November 2026: A as maziggy/bambuddy#3641, B as maziggy/bambuddy#3642, C as https://github.com/maziggy/bambuddy/issues/2933#issuecomment-7033784133. Nothing assigned yet, no code yet. Three parts:

- **A. Feature:** readable notifications (structured fields, colour dots), new issue.
- **B. Bug:** the queue notification shows the raw code `filament_short`, a small separate bug report.
- **C. Comment on #2933** (open, "Notification language localization"): notifications always arrive in English. A new issue would be a duplicate, so this adds our use case there.

Searched before: "notification language", "notification translate", "discord embed", "notification format", "filament_short". Related: #2933 (language), #2904 (Discord avatars), #1379 / PR #3546 / PR #3601 (more template variables), #3089 / PR #3199 (snapshots).

---

## A. Feature: readable notifications

**Title:** `[Feature]: Readable notifications: printer, job and filament as separate fields, with a colour dot`

### Problem or Use Case

On a phone, a queue notification in Discord is one block of text:

```
Queue Job Waiting
Blanket_Coaster_4x.P1s_gcode waiting for P1S
No matching material/color. Waiting on PLA (Lavender Purple)
```

```
Plate Clear Required
Sol P1s links: print finished. Confirm the build plate is clear before the queue continues.
```

With several printers in a farm I read every line to find out which printer it is and what I have to bring. Three things make it slow:

- Printer, job and the filament it waits for are run together in one sentence. "waiting for P1S" is the printer **model**, not the printer, so I don't know which of my P1S it means.
- The colour is only a name ("Lavender Purple"). I look for the spool by its colour, and a name from a catalog doesn't tell me which spool on the shelf it is.
- The Plate Clear message doesn't say which job finished.

Every Discord message is a green embed with a title and a description (`_send_discord`, fixed colour `0x00AE42`). All other channels get the same title and text.

### Proposed Solution

1. **Structured fields where the channel supports them.** Discord embeds get `fields` instead of one sentence:

   ```
   ⏳ Queue job waiting
   Printer      Sol P1s links
   Job          Blanket_Coaster_4x.P1s_gcode
   Waiting for  🟣 PLA Lavender Purple (#B39DDB)
   ```

   ```
   ✅ Plate clear required
   Printer      Sol P1s links
   Finished     Blanket_Coaster_4x.P1s_gcode
   ```

   The job name stays exactly as it is in the queue (the file name carries information like "4x" and the model).

2. **A colour dot** in front of every filament: the nearest of 🔴 🟠 🟡 🟢 🔵 🟣 🟤 ⚫ ⚪ for its hex, plus the hex itself. The mapping can follow the colour families the inventory already sorts by (#2729, `colorFamily` in `utils/colors.ts`), ported to the backend. Where the event is about one filament, the embed's side colour can be that filament's colour instead of the fixed green.

3. **New template variables** so text channels (Telegram, ntfy, email, Pushover) can use the same information in their own templates: `{printer}` (the printer's name, also for queue events), `{filament_type}`, `{color_name}`, `{color_hex}`, `{color_emoji}`, `{slot}`, and `{job_name}` for Plate Clear Required. Default templates keep their meaning; they only use the new variables where it helps.

4. **No internal codes** in any message (see the bug report `filament_short`).

### Alternatives Considered

- **Only editing the templates:** the templates can't do it today: the queue event passes only `job_name`, `target_model` and a finished sentence `waiting_reason`, and Discord has no fields.
- **Markdown in the description:** works in Discord and Telegram, but not in ntfy, Pushover or SMS-like channels. Fields plus variables work for all.

### Feature Category

Notifications

### Priority

Would improve my workflow

### Contribution

- [x] I would be willing to help implement this feature

---

## B. Bug: the queue notification shows `filament_short`

**Title:** `[Bug]: "Queue Job Waiting" notification shows the internal code "filament_short" instead of a reason`

**Area:** Notifications / Print Queue

### Bug Description

When a queued job waits because a loaded spool has too little filament left, the notification shows the internal code:

```
Queue Job Waiting
KnittedPenguin.9x.A1.swap.jobox waiting for A1
filament_short
```

The other waiting reasons are sentences ("No matching material/color. Waiting on PLA (Lavender Purple)").

`_block_on_filament_deficit` in `backend/app/services/print_scheduler.py` passes `waiting_reason="filament_short"` to the notification. The deficit it has at hand (`FilamentDeficit`: slot, filament type, grams needed and left) is not used in the text.

### Expected Behavior

A sentence like "Not enough PLA in AMS A slot 2: 12 g left, 40 g needed", and the printer's name rather than only its model.

### Steps to Reproduce

1. Enable "Queue Job Waiting" notifications (Discord here).
2. Queue a job for a printer whose matching spool has less filament left than the job needs (with the queue's filament check on).
3. The notification shows `filament_short`.

### Printer Model / Firmware

A1 (seen with an A1; not printer-specific)

### Bambuddy Version

`<version from Settings > About>`

### Installation Method / OS

Docker, Ubuntu 24.04

### Screenshots

Discord notification (attach the cropped screenshot).

---

## C. Comment on #2933 (notification language)

> Same here with Discord: every notification arrives in English, although the interface is in German. Since #3625 the interface language is per browser, and **Settings > General > Default language** is the install-wide language, but no backend code reads it yet; only SpoolBuddy uses it.
>
> A possible way, if you are open to it:
> - Notifications use the install-wide **Default language**, optionally overridden per provider (a farm may send German to the team's Discord and English to a webhook).
> - Default templates that the user has not edited are shipped per language; edited templates stay as they are.
> - Waiting reasons from the scheduler become a code plus values (e.g. `no_matching_filament` with type and colour) and are rendered in that language, so the To do list in the UI could translate the same codes.
>
> That is roughly 150 strings (40 template titles and bodies, the event names, about 25 waiting reasons). I'd be happy to help with it.
