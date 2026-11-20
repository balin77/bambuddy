# Issue draft – UI crashes when the browser translates the page

**Status:** Posted on 20 November 2026 as maziggy/bambuddy#3647 (screenshots still to be attached by the user). Not assigned yet. Searched before: "insertBefore", "removeChild", "google translate", "notranslate", "translate crash", "UI Crash" — no matching issue (#2616 is a different crash). Fix prepared in the fork on `fix/browser-translate-crash` (from `upstream/dev`), commits `45dcb1cf1` (fix) and `50671d4e3` (changelog), CI green.

Template: Bug report. Fields below map to `bug_report.yml`.

---

**Title:** `[Bug]: UI crashes with "insertBefore … not a child of this node" when Chrome translates the page`

**Product:** Bambuddy

**Area:** Frontend / UI

### Bug Description

On a phone whose browser language is not the Bambuddy interface language, Chrome offers to translate the page. With the translation on, the UI soon falls back to the "UI Crash" screen:

```
NotFoundError: Failed to execute 'insertBefore' on 'Node':
The node before which the new node is to be inserted is not a child of this node.
```

Even the crash screen itself shows up translated ("UI Crash" → "Fallo de la interfaz de usuario", "Retry" → "Rever"), which shows the browser translation is active.

Chrome's translation replaces text nodes that React still owns; the next re-render tries to insert next to a node that is no longer there and throws. This is a known React + Google Translate issue.

Two things in Bambuddy make it likely:

- `index.html` declares `<html lang="en">` and never changes it, so a page shown in German or Spanish is still announced as English and Chrome offers to translate it.
- The page does not opt out of machine translation, although Bambuddy has its own language picker (since #3625 for every user).

### Expected Behavior

The browser does not machine-translate Bambuddy (the user picks the language in Bambuddy instead), and the UI does not crash.

### Steps to Reproduce

1. On an Android phone, set Chrome's language to Spanish (or any language other than Bambuddy's current one).
2. Open Bambuddy and accept Chrome's "Translate this page".
3. Use the app for a moment (e.g. the printer cards update, or navigate between pages).
4. The "UI Crash" screen appears with the `insertBefore` error.

### Proposed fix (prepared)

- `index.html`: `<html lang="en" translate="no">` and `<meta name="google" content="notranslate" />`.
- `frontend/src/i18n/index.ts`: keep `<html lang>` on the language in use (`i18n.on('languageChanged', …)`), so the browser knows the page is already in the reader's language.
- A Vitest test for both.

### Printer Model / Firmware

Not printer-specific.

### Bambuddy Version

`<version from Settings > About>`

### Installation Method / OS

Docker, Ubuntu 24.04. Client: Android phone, Chrome, Spanish.

### Screenshots

Attach the crash screen (the two phone screenshots, cropped).
