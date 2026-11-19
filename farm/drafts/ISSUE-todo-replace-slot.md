# Issue draft – To do list names the slot a filament can go into

**Status:** Posted on 19 November 2026 as maziggy/bambuddy#3634. Not assigned yet. Follow-up to #3615 / PR #3622. No existing issue found (searched "to do list replace filament slot", "which tray replace swap filament queue"; #1497 is about inventory totals, not slots).

---

**Title:** `[Feature]: To do list: say which slot a missing filament can go into`

### Problem or Use Case

The "To do" list of the queue (#3615) says which filament a printer waits for, for example **Load filament: PLA Pink**. It does not say where to put it.

On a printer with one AMS all four slots are usually full. Say they hold red, blue, white and green, and the next job needs pink. The entry tells me to load pink, but I have to work out myself which of the four spools may come out. To do that I open the queue, look at every job waiting for this printer and compare their colours with the slots. On a farm with several printers that is the slow part of the task, and a wrong guess (taking out a spool the next job needs) makes the queue wait again.

The scheduler already has both halves of the answer: the trays the printer reports, and the filaments of the jobs waiting for it.

### Proposed Solution

A **Load filament** entry for a printer names where the filament can go:

1. **A free slot**, if the printer reports one: "Free: AMS A slot 2".
2. Otherwise **the slots no waiting job needs**: "Can be replaced: AMS A slot 4 (PLA Green)". A slot counts as needed when a pending job that could go to this printer (pinned to it, or a model job whose model and location fit) matches it, by the same matching the scheduler uses. The slot the running print uses is never offered.
3. If every slot is needed, the entry says so ("Every loaded filament is needed by a waiting job"), so I know I have to choose and nothing is hidden.

Details:

- It is a hint, nothing is changed on the printer and no slot is reserved. The scheduler behaves as today.
- Several missing filaments on one printer share the list of free and replaceable slots; the entry does not assign each filament a slot.
- An entry for "Any <model>" keeps naming its printers as today; the hint is given per printer there, or left out if that gets too long on a phone.
- A printer that has not reported its trays (off, just connected) gets no hint.
- The external spool holder is named like a slot when it is the only place the filament can go.
- API: `GET /queue/todo` gets additive fields on the `load_filament` entry. No migration, no new setting.

### Alternatives Considered

- **Reading it from the printer card.** The card shows the slots, but not which jobs need them. That is the comparison I want to stop doing by hand.
- **Suggesting exactly one slot.** Simpler to read, but the choice between two unneeded spools is the user's (one may be nearly empty, one may be hard to reach). A short list keeps that choice.
- **Reserving the slot.** Out of scope: it would change scheduling.

### Feature Category

Print Queue

### Priority

Medium

### Mockups or Examples

```
A1 Left
  Load filament   PLA Pink
                  Can be replaced: slot 4 (PLA Green)
                  [Open printer]

P1S Right
  Load filament   PETG Black
                  Free: slot 2
                  [Open printer]

X1C
  Load filament   PLA Orange
                  Every loaded filament is needed by a waiting job
                  [Open printer]
```

### Contribution

I would implement this myself once #3622 is merged, with tests, translations for all locales and the wiki update.
