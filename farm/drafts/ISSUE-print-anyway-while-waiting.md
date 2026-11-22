# Issue draft – "Print anyway" for a job that waits for more filament

**Status:** Posted on 22 November 2026 as maziggy/bambuddy#3659; fixed by the maintainer in dev (3a38447a6) the same day. Follow-up to #3587 (PR #3627, merged) and #1496. Searched before: "print anyway waiting for filament loaded filament first", "needs more filament start anyway" (no match).

---

**Title:** `[Bug]: A job that waits because a spool is too short cannot be started with "Print anyway" when "Loaded filament first" is on`

### Product

Bambuddy

### Area

Print Queue / Scheduling

### Bug Description

Since #1496 a job whose spool holds too little filament is held, and I can still start it on purpose: the job is staged, **Start** shows "Not enough filament" with the slot and the grams, and **Print anyway** sends it.

With **Loaded filament first** on (#3587) that way out is gone. The same job is not staged, it waits for filament:

```
Waiting for filament: P1S right (needs more filament) | Busy: P1S left · priority in 60 h
```

The queue row has no Start button in this state, and the To do list (#3615) only says what to load. The edit dialog does not help either: it skips the spool warning when a job is edited. So there is no way in the UI to say "I know the spool is short, print anyway". The job stays where it is until its maximum wait is over, 60 hours in my case.

"Print anyway" can only be chosen when the job is **created**, and only for a specific printer. For a job that already waits, or one queued for any printer of a model, it cannot be chosen at all.

Why I want it: I often start a long print on a spool that will not last and swap it when the printer pauses, or the weight in my inventory is simply too low and I can see the spool is fine.

### Expected Behavior

A job that waits only because a spool is too short can be released in the state it is in, without deleting and re-creating it:

- On the **queue row** and on the job's entry in the **To do list**: an action **Print anyway**. It opens the same "Not enough filament" confirmation as Start (slot, grams left, grams needed) and, when confirmed, releases the job. For a job queued for any printer of a model it then goes to the first free printer that has the filament loaded, as if the spool were long enough.
- It needs the same permission as Start.
- The acknowledgement is the existing `skip_filament_check` on the queue item, which the scheduler already honours in the wait added by #3587. As far as I can see only the way to set it on a waiting job is missing: `PATCH /queue/{id}` accepts the field, the UI never sends it.
- It stays an acknowledgement for this job only, and is dropped as today when the job is moved to another printer.

### Steps to Reproduce

1. Settings → Queue: turn **Loaded filament first** on.
2. Load a spool that matches a job but, by the inventory, holds less than the job needs (here: 196 g left, the job needs 505 g).
3. Queue the job for any printer of that model.
4. The row reads "Waiting for filament: <printer> (needs more filament)". There is no Start button and no "Print anyway" anywhere.

### Printer Model

P1S (not printer-specific)

### Bambuddy Version

1.3.2 plus `dev` up to 21 November 2026, on a build of my fork (`balin77/bambuddy`, branch `farm`). The wait comes from #3587, which is in `dev`.

### Installation Method

Docker

### Operating System

Ubuntu 24.04

### Additional Context

Workaround today: delete the job, queue it again for one specific printer and confirm "Print anyway" in the print dialog.

I introduced the wait with #3587 and missed this, so I would like to fix it myself, with tests, translations and the wiki update.
