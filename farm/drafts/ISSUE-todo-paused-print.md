# Issue draft – To do list: show paused prints

**Status:** Posted on 20 November 2026 as maziggy/bambuddy#3648. Not assigned yet. Follow-up to #3615 (PR #3622). Searched before: "to do list paused print runout" (no match).

---

**Title:** `[Feature]: To do list: show prints that are paused and wait for a person (filament runout, errors)`

### Problem or Use Case

The "To do" list (#3615) shows what the **waiting** jobs need: a plate to clear, a filament to load, a click on Start. It does not show the most urgent case on a farm: a **running** print that has paused and waits for someone.

Seen on my farm: a spool ran empty during a print. The printer paused and waited for a new spool. The To do list was empty, because for the queue this printer is just "Busy", and the jobs behind it wait quietly. A paused printer blocks everything queued for it, and the list I look at to see where I am needed says nothing.

The same goes for a print paused by an error (clogged nozzle, tangled filament, open door) and for a print someone paused by hand and forgot.

### Proposed Solution

One more kind of entry in the To do list, per printer: **Print paused**. It stands first in the printer's group, since nothing else on that printer can move before it.

```
A1-3
  PRINT PAUSED
  Filament ran out: A2 (PLA Lava Red). Load PLA Lava Red into A2
  TintinLampe.3mf · 62 %

X1C-2
  PRINT PAUSED
  Nozzle is clogged
  Bracket.3mf · 18 %

P1S-1
  PRINT PAUSED
  Lid.3mf · 40 %
```

- **Filament runout:** the entry names the slot that ran out and the filament to load. Bambuddy already resolves both for the printer card (`expected_tray` / `previous_tray`, #2587); the list reuses that.
- **Paused by an error:** the entry shows the sentence of the active HMS error, as the printer card does.
- **Paused without a known reason** (by hand, or by the slicer's pause): just the print and its progress.
- The entry appears whether or not a job waits for that printer: the paused print is itself the work. It disappears on the next refresh after the print resumes, is stopped or ends.
- It counts in the list's badge, like the other entries.
- Visibility follows the list's existing rules: only printers in the caller's printer scope.
- Read-only: no new setting, no migration, one additive kind in `GET /queue/todo`. The scheduler's decisions do not change.

Not part of this issue: failed or finished prints, offline printers, and notifications (the HMS and runout notifications stay as they are).

### Alternatives Considered

- **Notifications only.** They exist and I use them, but a notification scrolls away. The list is the place that shows what is open right now, for whoever walks into the room.
- **Showing every HMS error.** Too broad: many are warnings that need nobody. A paused print is a clear, narrow rule.
- **A separate "Problems" list.** For the person walking through the farm it is the same question ("where am I needed?"), so one list is better than two.

### Feature Category

Print Queue / Scheduling

### Priority

Medium

### Contribution

I would implement this myself, on top of #3615, with tests, translations for all locales and the wiki update. It makes sense only once PR #3622 is merged.
