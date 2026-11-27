# Auf farm gebaut, aber noch ohne eigenes Issue oder ohne PR-Platz

Stand 27. November 2026. Nicht vergessen: Bevor der jeweilige Code upstream geht, braucht er ein Issue (oder einen festen Platz in einem bestehenden PR).

| # | Was | farm-Commits | Upstream-Stand | Wohin |
|---|---|---|---|---|
| 1 | **Print anyway in der To-do-Liste**, je Drucker; ein Modell-Auftrag startet auf genau dem gezeigten Drucker | `e50e7ff05`, `17a801366`, `802d795bb` | #3622 ist gemergt, die To-do-Liste auf dev hat **kein** Print anyway (#3659 nur in der Warteschlange) | eigenes Issue + kleiner PR, oder in #3726 Schritt 1 |
| 2 | **Leerer Slot nach Filament-Ende im pausierten Druck:** wie beim Einsetzen das AMS-Bild mit Ziel-Slot und benötigtem Filament zeigen | (in Arbeit) | Pausierter Druck in der To-do-Liste ist #3648, Bild ist #3726 | als Erweiterung zu #3648 bzw. Folge-PR Resume/Stop; im Issue #3648 oder neuem Issue erwähnen |
| 3 | To-do-Eintrag wurde ~10-mal wiederholt (React-Key), Bild nur einmal | `ac8d7bc3f` | betrifft nur den noch nicht eingereichten #3726-Code | geht mit #3726 Schritt 1 mit, kein eigenes Issue |
| 4 | Slot im To-do-Bild öffnet das Slot-Menü der Druckerkarte statt Knopfreihe | `0d4d48a5a` | nur #3726-Code | in PR-3726.md erwähnen |
| 5 | Modell-Auftrag: To-do-Eintrag zeigt zuerst den freien Drucker; keine Düsen-Beschriftung bei Einzeldüse | `919a15596`, `a24d76643` | nur #3726-Code | in PR-3726.md erwähnen |
| 7 | To-do-Bild: Slot ohne RFID zeigt keinen AMS-Prozentwert mehr (Platzhalter 100 %, wie #3738) | (siehe Commit "To do picture … RFID") | nur #3726-Code | beim Neuaufbau von `feature/queue-todo-ams-picture` mitnehmen |
| 6 | Spulenformular liest `hasPermission` (useAuth) | `338b194ce` | nur farm (Port-Fehler) | kein Issue nötig |

Ergänzen, sobald der Nutzer weitere Punkte nennt.
