# Issue draft – inventory filament for a specific printer

**Status:** Posted on 20 November 2026 as maziggy/bambuddy#3649. Not assigned yet. Follow-up to #3590 (PR #3618). Searched before: "filament override specific printer inventory queue" (no match).

---

**Title:** `[Feature]: Print dialog: pick a filament from the inventory also for a specific printer (Queue / Schedule)`

### Problem or Use Case

With #3590 (PR #3618) the print dialog can queue a job in a colour from the inventory that is not loaded yet. That works only in the mode "any printer of this model". As soon as I pick a **specific printer**, the dialog shows the slot mapping instead, and each filament can only be mapped to a slot that is loaded on that printer right now.

On my farm I often want exactly the combination that is missing: "this printer, but in Pastel Ice from the shelf". The printer is fixed (it has the right plate, nozzle or plate changer), the colour is in stock but not loaded. Today I have two workarounds, both poor: load the spool first and come back to the dialog, or queue for the model and hope the scheduler picks the printer I meant.

### Proposed Solution

In the slot mapping of a specific printer, when the job goes to **Queue** or **Schedule** (not "Now"), each filament's dropdown gets a second group below the loaded slots:

```
PolyTerra PLA (146.4 g)   →  [ A3: PolyTerra PLA Matte (Pastel Ice) - 395 g left   v ]
                               Loaded now
                                 A1: PolyTerra PLA Matte (Cotton White) - 227 g left
                                 A3: PolyTerra PLA Matte (Pastel Ice) - 395 g left
                               From inventory (not loaded)
                                 PolyTerra PLA Matte (Lava Red) - 1 spool, 850 g
                                 PolyTerra PLA Matte (Army Beige) - 2 spools, 1.4 kg
```

- Picking an inventory entry stores a forced filament override for that filament instead of a slot, the same data a model job gets from #3590. The job then waits with "Waiting for filament" until the colour is loaded on that printer, and starts on its own once it is. The To do list (#3615) shows it like any other filament wait.
- The list is the one from #3590: same entries, same stock warning, and the same "Show inventory colours" setting switches it off.
- With **Now** the group is not offered: a print that starts at once can only use what is loaded.
- Filaments left on a loaded slot keep their slot mapping as today. Only the picked one waits.
- No new setting, no migration: `filament_overrides` and the forced match already exist on queue items.

### Alternatives Considered

- **Queue for the model and narrow by location.** Works only when the location holds one printer of that model, and it is not what the dialog suggests.
- **Load first, then queue.** That is the order the feature in #3590 was meant to remove: I want to queue at the desk and load on the next round.

### Feature Category

Print Queue / Scheduling

### Priority

Low

### Contribution

I would implement this myself, with tests, translations for all locales and the wiki update. It builds on #3590, so it makes sense only once PR #3618 is merged.
