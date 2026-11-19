# Issue draft – finer printer permissions

**Status:** Posted on 19 November 2026 as variant A, a comment on maziggy/bambuddy#3248 (https://github.com/maziggy/bambuddy/issues/3248#issuecomment-7003089748). No assignment yet; maintainer asked for 👍 on #3248.
Two ways to post, the user decides:
- **A (recommended):** a comment on #3248 that widens it (text at the end of this file), so it is not closed as a duplicate.
- **B:** a new issue that references #3248 (text below).

---

## Variant B – new issue

**Title:** `[Feature]: Finer printer permissions: allow pause/resume, plates and spools without full printer control`

### Problem or Use Case

In a print farm, helpers do a few tasks at the printers: they pause and resume a print, confirm that a plate is clear, load spools and assign them to AMS slots. They should not change temperatures, move axes, start a calibration, abort prints or reconnect printers.

Today one permission, `printers:control`, covers all of these at once. A group that should only pause and resume also gets:

- stop print and skip objects
- nozzle, bed and chamber temperature, fan speed, print speed, airduct mode, chamber light
- XY, Z and extruder jog, home axes, select extruder
- AMS load and unload, slot configure, tray reset, AMS backup
- drying start and stop, deleting a scheduled drying
- calibration and print options
- HMS clear and HMS actions
- connect and disconnect, MQTT logging (#3248)

So an admin can either give helpers everything or nothing. Assigning a spool from the inventory already works with `inventory:update` alone, but the slot's **Configure** button on the printer card still needs `printers:control`.

#3248 asks for the same thing for the admin and debug actions (reconnect, refresh, MQTT debug, diagnostic). This request is the general form: a small set of task-shaped permissions instead of one switch.

### Proposed Solution

Split `printers:control` into task-shaped permissions and keep `printers:control` as the umbrella that still grants all of them:

| Permission | Covers |
|---|---|
| `printers:pause_resume` | pause, resume |
| `printers:stop` | stop print, skip objects |
| `printers:clear_plate` (exists) | confirm the plate is clear; also the plate-changer refill once #3575 lands |
| `printers:filament` | AMS load and unload, slot configure, tray reset |
| `printers:tune` | temperatures, fans, print speed, airduct mode, chamber light |
| `printers:motion` | jog XY / Z / extruder, home axes, select extruder |
| `printers:drying` | drying start and stop, scheduled dryings |
| `printers:maintenance` | calibration, print options, HMS clear and HMS actions, AMS backup |
| `printers:admin` (#3248) | connect, disconnect, refresh, MQTT logging, diagnostic |

- **Backward compatible without touching existing groups:** an action is allowed with either its own permission **or** `printers:control`. Every group that has `printers:control` today keeps exactly what it has. No migration of group rows is needed.
- The group editor shows the new permissions under Printers, next to Control Printers. Ticking Control Printers ticks them all.
- The printer card hides or disables each control based on its own permission (same pattern as `printers:clear_plate` today).
- The backend enforces every permission per route. Printer scope (#1727, #3108) still applies.
- API keys follow the same rule.

Example group "Farm helper": `printers:read`, `printers:pause_resume`, `printers:clear_plate`, `printers:filament`, `inventory:read/create/update`, `filaments:read`. No settings, queue, library or archive permissions.

### Alternatives Considered

- **Only #3248's admin/debug split:** helps schools, but helpers would still be able to abort prints, change temperatures and move axes.
- **One extra permission for pause/resume only:** solves one case; the next request (plates, spools, drying) needs another change.
- **Removing Control Printers from helpers:** then they cannot pause a print or configure a slot.

### Feature Category

Other (users and permissions)

### Priority

Would improve my workflow

### Mockups or Examples

Group editor, Printers card:

```
[x] Read Printers
[ ] Control Printers (all of the below)
    [x] Pause and resume
    [ ] Stop print
    [x] Clear plate
    [x] Filament (load, unload, slot configure)
    [ ] Temperatures, fans, speed, light
    [ ] Move axes
    [ ] Drying
    [ ] Calibration and maintenance
    [ ] Connection and debug (#3248)
```

### Contribution

- [x] I would be willing to help implement this feature

Related: #3248, #1727, #3108, #3575.

---

## Variant A – comment on #3248

> I'd like to add a farm use case to this, which points the same way but a bit wider.
>
> In a print farm, helpers pause and resume prints, confirm cleared plates and load and assign spools. Today that needs Control Printers, which also lets them abort prints, change temperatures, move axes, run calibrations, start drying and reconnect printers.
>
> Would you consider splitting `printers:control` into a few task-shaped permissions, with `printers:control` kept as the umbrella? For example: pause/resume, stop, clear plate (exists), filament (load, unload, slot configure), tune (temperatures, fans, speed, light), motion (jog, home), drying, maintenance (calibration, HMS) and admin/debug (the actions in this issue).
>
> A route would accept either its own permission or `printers:control`. Existing groups would keep exactly what they have, with no migration of group rows. I'm happy to implement it if you're open to it.
