# Issue draft – language picker for every user

**Status:** Posted on 19 November 2026 as maziggy/bambuddy#3623. Not assigned yet. No existing issue found (searched "language per user", "language user menu", "language permission settings").

---

**Title:** `[Feature]: Let every user choose the interface language, without settings permissions`

### Problem or Use Case

The language picker lives only in Settings > General. A user without `settings:read` cannot open that page, and even with access the picker refuses to change without `settings:update`.

So a restricted user, for example a farm helper who only manages spools, cannot switch the interface to their language. The only ways today are:
- changing the language of the phone or browser and clearing Bambuddy's site data, so the detector picks it up again; or
- an admin signing in on the helper's device and changing it there.

The second way has a side effect. The picker also saves the install-wide `language` setting, which notifications and SpoolBuddy use. Changing it for one helper changes it for everyone.

The interface language is already stored per browser (`bambutrack_language` in localStorage), and the detector falls back to the browser language. Only the picker is in the wrong place.

### Proposed Solution

1. **A language entry in the user menu** (header and sidebar), available to every signed-in user and when auth is off.
   - It changes only the interface language of this browser (localStorage), like the picker does today.
   - It never writes the install-wide setting.
2. **Settings > General keeps the picker as "Default language"** for admins (`settings:update`).
   - It sets the install-wide language used by notifications and SpoolBuddy.
   - It does not override what a user picked in their own menu.
   - Optionally, it also becomes the interface language for browsers where nobody has picked one, instead of the browser language. That is a behaviour change, so keep it behind the existing detection order unless the maintainer prefers otherwise.
3. **No permission and no migration** needed; it is a frontend change plus i18n strings.

### Alternatives Considered

- **Giving helpers `settings:update` so they can use the existing picker:** this exposes all settings, and every switch changes the language for everyone.
- **A per-user language stored on the server:** works across devices, but needs a migration and a rule for installs without authentication. It could come later; the per-browser picker solves the common case now.

### Feature Category

UI/UX

### Priority

Would improve my workflow

### Mockups or Examples

User menu:

```
Signed in as helper
───────────────
Language: Deutsch ▾
Change password
Sign out
```

### Contribution

- [x] I would be willing to help implement this feature
