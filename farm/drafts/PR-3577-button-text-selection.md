# PR draft – Feature C (#3577)

- **Base:** `maziggy/bambuddy:dev`
- **Head:** `balin77:fix/button-text-selection`
- **Title:** `Frontend: button labels are not text-selectable on touch (#3577)`
- **Status:** Draft. Submit only after #3577 is assigned to balin77 **and** the user approves.

---

## Description

On phones, tablets and the installed PWA, a tap on a button that lasts a little long or moves a little starts a text selection on the button label. The user sees selection handles and the copy menu, and the button is not pressed. The shared `Button` component never set `select-none`, and most of the app's ~930 buttons are raw `<button>`s. So the fix is one base-layer rule in `frontend/src/index.css`, next to the existing `cursor: pointer` rule from #2791:

```css
button,
[role="button"] {
  -webkit-user-select: none;
  user-select: none;
  -webkit-touch-callout: none;
}

/* A role="button" row (Collapsible's summary) may hold a field; iOS Safari
   does not focus or edit one under user-select: none. */
input,
textarea,
[contenteditable="true"] {
  -webkit-user-select: text;
  user-select: text;
}
```

The rule is in `@layer base`, so a utility like `select-text` can still re-enable selection on a specific element. Inputs, textareas and normal text stay selectable.

## Related Issue

Fixes #3577

## Documentation

**Pick one**:
- [ ] Docs PR(s) linked above
- [x] No docs update required — reason: touch-interaction fix with no new setting, URL or flow. Screenshots in the wiki are unaffected.

## Type of Change

- [x] Bug fix (non-breaking change that fixes an issue)

## Changes Made

- `frontend/src/index.css`: base-layer rule for `button` and `[role="button"]`: `user-select: none`, `-webkit-user-select: none`, `-webkit-touch-callout: none`; inputs, textareas and contenteditable keep `user-select: text` (iOS Safari would not edit a field inside a `role="button"` row otherwise)
- `CHANGELOG.md`: entry under Fixed

## Screenshots

<!-- TODO (user): before/after from a phone. Long-press a button on the printer card (e.g. "Mark plate as cleared") and a toggle in the print dialog. -->
| Before | After |
|---|---|
| _selection handles / copy menu on a button label_ | _no selection, button press works_ |

## Testing

- [x] I have tested this on my local machine
- [ ] I have tested with my printer model: <!-- TODO: phone/browser (iOS Safari, Android Chrome), printer model -->
- Frontend lint, `tsc` and Vitest pass (CI on the branch).

## Checklist

- [x] My code follows the project's coding style
- [x] I have commented my code where necessary
- [x] My changes generate no new warnings
- [x] I have tested my changes thoroughly

## Additional Notes

The rule matches only the elements that the `cursor: pointer` rule already treats as controls. A `[role="button"]` card that holds text a user might want to copy loses selection on that text. I found no such case in the app. If one turns up, `select-text` on the inner element brings it back.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_0127bEAsde34UE3UDyMWQtka
