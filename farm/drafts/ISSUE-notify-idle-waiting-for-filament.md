# Issue draft – notify when a printer stands idle for filament

**Status:** Draft, not posted. Follow-up to #3587 (merged) and #3641/#3642 (ours, assigned, PRs not opened yet). Searched before: "notification printer idle waiting for filament" (no match).

---

**Title:** `[Feature]: Notify when a printer stands idle because its jobs wait for filament, and at once when a spool is too short`

### Problem or Use Case

With **Loaded filament first** and a maximum wait (#3587), a job that waits for filament is announced once: when it gains priority. Until then Bambuddy stays quiet. I asked for that, so that a skipped job does not ping me while its printer keeps printing other jobs.

On my farm it turned out to be too quiet in two cases:

1. **Everything stands still.** A printer is idle, jobs wait for it, and none of them can start because a filament is missing. With a maximum wait of 60 hours I get no message for 60 hours, although a printer is doing nothing. With several printers in that state the whole farm stands and my phone says nothing. Only the To do list shows it, and only when I look.
2. **A spool is too short.** A job waits because the matching spool does not hold enough. This never resolves by itself: either I change the spool or I decide to print anyway (#3659). I only learn about it when the job gains priority.

### Proposed Solution

Three rules instead of one:

1. **A new event "Printer idle: waiting for filament"**, with its own checkbox per provider (on by default). It fires when a printer has been idle for 5 minutes, has pending jobs that could run on it, and none of them can start because filament is missing or too short. One message per printer and standstill; again only after the printer has printed in between or the list of filaments changed.

   ```
   Printer idle: waiting for filament
   P1S right has nothing it can print. 2 jobs wait for filament.
   Printer   P1S right
   Load      PLA Lava Red (A3 has 196 g, needs 505 g)
             PLA Army Beige
   Jobs      Lamp base · Santa box
   ```

2. **A spool that is too short is announced at once**, once per job, whatever the maximum wait says (the existing "Queue Job Waiting" event):

   ```
   Queue Job Waiting
   Lamp base waiting for P1S
   Not enough PLA Lava Red on P1S right: A3 has 196 g, the job needs 505 g
   ```

3. **Quiet stays what does not stand still.** A job skipped while its printer prints other jobs sends nothing, as today. The message when a job gains priority stays as the second step.

Details:

- The 5 minutes keep the event from firing between two jobs of a printer that is merely changing over.
- A printer waiting for a plate confirmation, a plate changer refill or a sensor interlock is not "idle for filament"; those have their own events.
- Without Loaded filament first nothing changes for the existing events.
- The new event gets a default template like the others, with the variables of #3641 where that is merged.
- Data: one boolean column on the notification providers (additive migration, default true), like the other event switches.

### Alternatives Considered

- **Announcing every job that starts to wait for filament.** That is the noise #3587 removed: on a farm most skipped jobs need nobody.
- **Shortening the maximum wait.** It changes the order of the queue, not when I am told.
- **One farm-wide message "prints are waiting for filament".** It does not say where to go. One message per idle printer does.

### Feature Category

Notifications

### Priority

Medium

### Contribution

I would implement this myself, with tests, translations for all locales and the wiki update. It reads best on top of #3641.
