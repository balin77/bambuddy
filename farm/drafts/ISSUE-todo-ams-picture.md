# Issue draft – To do list: AMS picture and actions in place

**Status:** Posted on 24 November 2026 as maziggy/bambuddy#3726. Not assigned yet. Follow-up to #3615 (PR #3622), #3634, #3640, #3648. Searched before: "to do list assign spool AMS slot picture" (no match).

---

**Title:** `[Feature]: To do list: show the AMS with where each spool goes, and let me assign the spool and act on an entry right there`

### Problem or Use Case

The To do list (#3615) tells me what a printer needs. With #3634 it also says in words where a filament can go: "Replace: A3 (PLA Lava Red, 196 g left)", "Free: A1, A4".

Using it on my farm I noticed two things:

1. **The words take a moment to map onto the machine.** Standing at the printer with a spool in my hand, I want to see the four slots and which one the spool goes into, not read a sentence and count.
2. **For most entries the list only tells me, I still have to go elsewhere to act.** After loading a spool I open the printer card to assign the inventory spool to the slot. A paused print I resume on the printer page. A smart plug that failed I retry in its own dialog. The list knows exactly what I am about to do; it could offer it.

### Proposed Solution

**1. A picture instead of the sentence.** A "Load filament" entry shows the printer's AMS as a row of slots with what is in them, and above it the spools to load, each one in the column of the slot it goes into, with an arrow down. A spool is always drawn above its own slot, so arrows never cross.

```
                    [ PLA Lava Red ]
                    [ new, 505 g+  ]
                            |
                            v
 AMS A
 [ A1        ] [ A2        ] [ A3          ] [ A4    ]
 [ Cotton    ] [ Army      ] [ Lava Red    ] [ empty ]
 [ White     ] [ Beige     ] [ 196 g · out ] [       ]
 [ 227 g     ] [ 640 g     ] [             ] [       ]

 [ Assign spool for A3 ]  [ Print anyway ]  [ Edit job ]
```

Slot states in the picture: stays, goes out (replaced), empty, matches already, and locked (the running print uses it). The states are the ones #3634 and #3640 already work out; this changes how they are shown.

- A printer with several AMS units shows the units something goes into; the others are collapsed.
- A job queued for any printer of a model shows the picture for the printer it would go to next, with a switch to the other candidates.
- On a phone the four slots fit the width without sideways scrolling.

**2. Assign the spool in the list.** "Assign spool for A3" opens the matching spools of the built-in inventory inside the entry: the ones that cover the job first, each with weight and storage location, one tap to assign it to that slot. Also "Scan label" (the QR scanner, assigning to the same slot) and "New spool". It uses the existing assignment, permissions included.

**3. The other entries can be acted on in place**, each button only for a user who holds the permission:

| Entry | Today | Proposed |
|---|---|---|
| Print paused (runout, error) | text | Resume, Stop |
| Load filament | text, link to the printer | Assign spool, Configure slot (type and colour for a spool without RFID) |
| Job does not fit the printer | nothing | Edit job (other colour), Move to another printer |
| Colour not in inventory | hint | New spool |
| Smart plug failed to power on | text | Power on again |
| Plate clear, plate changer empty, staged job | buttons | unchanged |

A sensor interlock stays a hint with a link: that one needs a hand at the machine.

No new setting and no migration: the list gets the slot contents it needs with `GET /queue/todo`, everything else calls endpoints that exist.

### Alternatives Considered

- **Keeping the sentence and adding the buttons only.** The picture is the part that saves the most time at the machine.
- **Linking to the printer card with the slot highlighted.** It still leaves the list, and on a phone the card is long.

### Feature Category

Print Queue / Scheduling

### Priority

Medium

### Contribution

I would implement this myself, with tests, translations for all locales and the wiki update, in steps: the picture and the spool assignment first, the remaining actions after. It builds on #3615 and #3634, so it makes sense only once those are merged. I have mock-ups and can attach them.
