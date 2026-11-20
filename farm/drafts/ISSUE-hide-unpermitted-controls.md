# Issue draft – hide the controls a group may not use

**Status:** Posted on 20 November 2026 as maziggy/bambuddy#3639. Not assigned yet. No existing issue found (searched "hide disabled buttons permission", "hide controls without permission simplified view").

---

**Title:** `[Feature]: Per-group option to hide the printer controls a user has no permission for`

### Problem or Use Case

A user without the permission for a printer action sees its button greyed out. That is a good default: it shows the function exists.

For a helper on a print farm it is the opposite of helpful. A helper who may only clear plates and pause a print sees a printer card full of controls that never work for them: stop, speed, temperatures, calibration, drying, connect and disconnect. On a phone the three buttons they do use are hard to find among the disabled ones, and every disabled button is a question to the admin ("why can't I press this?").

I would like to give such a group a simpler printer card that shows only what the group can use.

### Proposed Solution

A checkbox per group, at the bottom of the permission list on the group edit page: **Hide controls this group cannot use**. Off by default, so nothing changes for existing groups.

When it is on for a user:

- A control on the printer card (and in the dialogs opened from it) that is disabled **only because the user lacks the permission** is not rendered.
- A control that is disabled for another reason (printer offline, print running, request pending) stays visible and greyed, as today. Otherwise the card would change shape all the time.
- A section whose controls are all hidden disappears with them, so no empty frames or headings remain.

Details:

- A user in several groups gets the simple view only when every one of their groups has the option on. Admins and installs without authentication are unaffected.
- It is a display option, not a security boundary: the server keeps enforcing the permissions exactly as today.
- Data: one boolean on the group (like `restrict_printers`), an additive migration with default false, returned with the user's permissions so the frontend needs no extra request.
- Scope of this issue: the Printers page. Other pages can follow the same hook later if wanted.

### Alternatives Considered

- **A global setting.** I do not want it as a general rule: admins and regular operators should keep seeing what exists.
- **A per-user preference.** The need is tied to the role, not the person, and the admin sets it up for the helpers.
- **Always hiding instead of greying.** Changes the behaviour for everyone and hides features from users who might ask for access.

### Feature Category

User Management / Permissions

### Priority

Low

### Mockups or Examples

```
Group "Helpers"                       Printer card for a helper
[x] Printers: read                    today:   [Pause] [Stop] [Speed] [Light] [Calibrate] [Clear plate]
[x] Printers: clear plate                       (four of them greyed)
[x] Printers: control ...             with the option:
...                                            [Pause] [Clear plate]
[x] Hide controls this group cannot use
```

### Contribution

I would implement this myself, with tests, translations for all locales and the wiki update.
