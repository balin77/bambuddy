# Issue draft – To do list: prepare the next jobs' filaments, also during a print

**Status:** Draft, nothing posted. Follow-up to #3615 (PR #3622) and #3634. Code is prepared in the fork on `feature/queue-todo-prepare` (on top of `feature/queue-todo-replace-slot`). Searched before: "prepare filament next job", "load filament during print queue", "swap spool while printing".

---

**Title:** `[Feature]: To do list: prepare the filaments of a printer's next jobs, also while it prints`

### Problem or Use Case

The "To do" list (#3615) tells me what a printer waits for **now**, and with #3634 where the filament can go. It doesn't tell me what comes **next**.

In a farm a printer usually prints while I walk past it. Say it prints a job with red and white, and the next job for it needs blue and green, which are not loaded. Today I only learn that when the print has finished and the next job is held: the printer stands idle until I come back with blue and green.

A Bambu AMS lets me swap a spool that the running print doesn't use. So I could load blue and green **during** the print, if the list told me which spools the next job needs and which slots the running print doesn't touch.

### Proposed Solution

A second, quieter kind of entry in the To do list, per printer: **Prepare**.

```
X1C-2                        (printing, 1 h 20 m left)
  Prepare   Next: Bracket needs PETG Black, PLA Blue
            Can be replaced now: A3 (PLA Yellow), A4 (PLA Green)
            Then: Lid needs PLA White · Free: B2
```

- **Which jobs:** the next one or two jobs of that printer, in the order the queue would take them: jobs pinned to the printer, and model jobs that can only go to this one printer. A model job that several printers could take is left out, since it is not known which printer gets it.
- **Which slots:** the same rules as #3634, plus:
  - never a slot the running print uses;
  - never a spool that the printer would switch to when the running spool runs out (AMS filament backup on: same filament and colour on the same nozzle);
  - never a slot that a nearer job needs. The next job is served before the one after it.
- **Low key:** Prepare entries don't count in the To do badge and send no notification. They are a suggestion, not something the queue waits on.
- If the printer doesn't report what the running print uses (for example a print started from the slicer, whose mapping is unknown), there is no Prepare entry. The list never guesses.
- API: additive `prepare` list per printer group on `GET /queue/todo`. No migration, no new setting.

### Alternatives Considered

- **Asking to load everything at once when the printer waits:** an idle printer already lists one "Load filament" entry for every job that waits for it, so that case is covered. The gap is the printer that is busy.
- **Reserving slots for the next job:** out of scope, it would change scheduling.
- **Looking further ahead than two jobs:** the further ahead, the less certain, and the list would get long on a phone.

### Feature Category

Print Queue

### Priority

Would improve my workflow

### Mockups or Examples

See above.

### Contribution

- [x] I would be willing to help implement this feature (prepared in my fork, after #3622 and #3634).
