# Plan: Sprache der Benachrichtigungen (#2933)

Status: nur Plan, kein Code. #2933 ist dashu33 zugewiesen; Umsetzung erst nach Freigabe durch den Nutzer und Abstimmung im Issue.

Stand: `upstream/dev` vom 21.11.2026. #3615 wurde auf `origin/feature/queue-todo-list` gelesen, #3641 auf `origin/feature/notification-readable`.

## 1. Was übersetzt werden müsste

| Quelle | Ort | Anzahl |
|---|---|---|
| Standardvorlagen: Titel und Text | `backend/app/models/notification_template.py:27-292` (`DEFAULT_TEMPLATES`) | 40 Ereignisse, also 40 Titel und 40 Texte (80 Strings) |
| Anzeigenamen der Ereignisse | `backend/app/api/routes/notification_templates.py:28-73` (`EVENT_NAMES`), dazu `"name"` in jeder Vorlage | 40 |
| Wartegründe des Schedulers (Teilsätze und Muster) | `print_scheduler.py` (Stellen unten) | ca. 26 |
| Abbruchgründe, die als `{reason}` in Benachrichtigungen landen | `print_scheduler.py:1279`, `:1338`, `:2606`, `:9487`, `:10267`, `:10275`, `:10593`, `:11437`, `:11743` u. a. | ca. 12 |
| Hilfstexte | `notification_service.py`: `"Unknown"` 17-mal (eine Bedeutung), `_format_duration` `:356-364` (`{h}h {m}m`), `_format_eta` `:302-315`, `"No details available"` `:2218` | ca. 5 |
| Testbenachrichtigung | `notification_service.py:427-428`. Doppelt vorhanden, auch als Vorlage `test` im Modell | 2 |
| Tasten und Hinweise | ntfy Good/Reject (`:1489-1490`), Pushover `"Confirm print outcome"` (`:1504`), Telegram-Tasten (`:1525-1526`), `TELEGRAM_REACTION_HINT` (`:51`), Daily-Digest-Titel und Gruppenüberschriften (`:3189`, `:3201`) | ca. 7 |
| Nur mit #3641: Discord-Feldnamen und Farbfamilien | `notification_service.py` (Printer, Job, Finished, Slot, Filament, Remaining), `utils/color_utils.py` (Farbfamilien wie „Red“) | ca. 6 + 15 |
| **Summe** | | **ca. 170-190 je Sprache** |

Die Schätzung von ~150 aus unserem Kommentar vom 20.11. ist damit etwas zu niedrig. Das Frontend kennt nur 10 Ereignisnamen (`notifications.eventTypes`, `en.ts:7733`). Wiederverwenden lässt sich davon kaum etwas.

Wartegründe im Einzelnen:
- `Busy:` mit den Zusätzen „(drying)“ und „kept free…“: `:2220`, `:2480`, `:2598`, `:2702`, `:4292`, `:6352`
- `Offline:` und `Offline, no Auto On smart plug:`: `:2554`, `:2566`, `:4294`, `:4299`
- `Waiting for plate confirmation:` `:6351`, `Waiting on {interlock}` `:2465`
- `Waiting for filament:`, `No matching material/color` und die Prioritätszusätze: `:765-777`, `:4265`, `:4280`
- `No active/available {model} printers`: `:4059`, `:4301`; Düsenmeldung `:4250`
- `File was sliced for…` `:2802`, `MODEL_GATE_WAIT_REASON` `:683`, `Needs {wanted}` `:10063`
- vier Meldungen zu abgelehnten Uploads `:466-485`
- die Verknüpfungen `"{model}: "` und `" | "` in `:686-718`

## 2. Wartegründe als Code plus Werte

Heute ist der Wartegrund ein englischer Satz (`print_queue.py:29`, `Text`). Er ist gleichzeitig ein Vertrag, den mehrere Stellen per Textvergleich auslesen:
- `_is_busy_only` (`:4304`) und `_asks_nothing_new` (`:491`) entscheiden darüber, ob benachrichtigt wird
- `_is_unmatched_hold_reason`, `_is_filament_wait`
- im Frontend `isBusyOnlyWaitingReason` (`utils/waitingReason.ts:16-23`), `QueueTimelineView.tsx:140` und der Gleichheitsvergleich mit `MODEL_GATE_WAIT_REASON` (`QueuePage.tsx:2690`)

Die Warteschlangen-Zeile zeigt `formatWaitingReason(item.waiting_reason, t)` an (`QueuePage.tsx:1070-1073`). Übersetzt werden dabei nur das Präfix „Waiting for filament:“, das Präfix „No matching material/color“ und der Prioritätszusatz (`waitingReason.ts:46-70`). Alles andere erscheint so roh, wie das Backend es schreibt.

Die Benachrichtigung bekommt denselben Satz unverändert als `{waiting_reason}` (`notification_service.py:2977`). Ohne Codes lässt er sich nur übersetzen, indem man ihn wieder zerlegt, und das ist brüchig. Codes sind also nötig.

**Vorschlag:** `waiting_reason` bleibt englisch und unverändert, als Vertrag und Rückfall. Daneben kommt eine strukturierte Liste:

```
waiting_parts: [{"code": "busy", "params": {"printers": ["P1"]}, "model": null}, ...]
waiting_suffix: {"code": "priority_in", "params": {"hours": 3}} | null
```

**Speicherung:** zunächst ohne DB-Spalte, nur im Speicher und berechnet. Vorbild ist `_filament_holds` aus #3615 (`print_scheduler.py:1542`, `:1952` auf dem Branch). Der Scheduler schreibt bei jedem Durchlauf neu (`hold_item`, `:2169-2186`). Nach einem Neustart fehlt die Liste darum höchstens einen Durchlauf lang, und die API liefert in der Zeit `null`. Das Frontend fällt dann auf `formatWaitingReason` zurück. Eine JSON-Spalte, also eine Migration in `database.py`, lohnt sich erst, wenn sich diese Lücke als störend erweist.

Für Codes gibt es schon ein Vorbild im Projekt: Das Trocknen speichert bereits reine Codes (`print_scheduler.py:7939-7974`), und das Frontend übersetzt sie (`PrintersPage.tsx:47-60`).

**To-do-Liste (#3615):** `queue_todo.py:3-7` liest den Wartegrund bewusst nicht aus und nutzt `FilamentHold`. Die Codes ändern daran nichts. `FilamentHold` sollte aber die `params` des Codes `filament_wait` bilden, damit es nicht zwei parallele Strukturen gibt. Deshalb erst nach dem Merge von #3615 darauf aufbauen. Die Textprüfungen (`_is_busy_only` usw.) können später auf Codes umgestellt werden, aber nicht in diesem Schritt.

## 3. Unveränderte und bearbeitete Vorlagen

`is_default` taugt dafür nicht. Es wird nur beim Seeden gesetzt (`database.py:8034`, `:8046`, immer `True`). `update_template` (`notification_templates.py:117-141`) und `reset_template` (`:144-174`) fassen es nie an. Es steht also auch bei bearbeiteten Zeilen auf `True` und wird trotzdem ausgeliefert (`schemas/notification_template.py:581`).

Zuverlässig ist nur der Textvergleich. Dafür gibt es schon Vorbilder:
- die Migrationen in `database.py:7450-7470` ändern nur Zeilen, für die `WHERE body_template = :old` zutrifft
- #3641 bringt `is_unmodified_template()` mit (`notification_content.py:24`, `:35`), vergleicht aber nur mit der englischen Fassung

**Vorschlag:** Die DB-Zeilen bleiben unverändert. Beim Rendern gilt: Stimmen Titel und Text mit der Standardfassung irgendeiner Sprache überein, wird die Standardfassung der Zielsprache genommen. So funktioniert auch ein späterer Sprachwechsel. Bearbeitete Zeilen bleiben unberührt. `is_unmodified_template` wird so erweitert, dass es gegen alle Sprachen vergleicht. Der Vorlagen-Editor sollte ein berechnetes Feld `is_customized` und die Vorschau in der Zielsprache bekommen. Sonst zeigt er englischen Text, verschickt wird aber deutscher.

## 4. Sprache für die ganze Installation oder pro Anbieter

- `language` (`schemas/settings.py:128`) liest im Backend niemand. Im Frontend liest es nur `SpoolBuddyLayout.tsx:42-48`. Die Einstellung in Einstellungen > Allgemein (`SettingsPage.tsx:1887-1915`) heißt inzwischen „SpoolBuddy display language“ (`en.ts:2449-2450`). Ihr Hilfetext sagt ausdrücklich, dass jede Person ihre UI-Sprache selbst wählt.
- `notification_language` (`schemas/settings.py:129`, Beschreibung „en, de“) gibt es schon. Gelesen wird es nirgends, eine UI dazu gibt es nicht. Es kommt nur im Test `test_settings_api.py:378` vor.

**Empfehlung:** Wir schlagen vor, die verwaiste Einstellung `notification_language` zu nutzen statt `language`. Sonst steuert ein Feld, das „SpoolBuddy“ im Namen trägt, die Benachrichtigungen. Der Rückfall wäre `notification_language` → `language` → `en`. Einstellungen sind Schlüssel-Wert-Paare, deshalb braucht das keine Migration. Gezeigt wird die Einstellung unter Einstellungen > Benachrichtigungen. Das weicht von unserem Kommentar vom 20.11. ab und muss im Issue angesprochen werden.

Eine Sprache pro Anbieter (nullable Spalte `language` auf `notification_providers`) bräuchte eine Migration. Sie kommt erst, wenn jemand sie wirklich braucht.

## 5. i18n im Backend ohne neue Abhängigkeit

Die Frontend-Locales sind TypeScript (16 Dateien unter `frontend/src/i18n/locales/`). Python kann sie zur Laufzeit nicht ohne Node lesen.

**Vorschlag:**
- je Sprache eine JSON-Datei unter `backend/app/i18n/notifications/<code>.json`, für die 16 Sprachen
- ein kleiner Helfer `translate(key, lang, **params)`, der pro Schlüssel auf `en` zurückfällt
- ein Paritätstest in `backend/tests/unit/` nach dem Muster von `frontend/scripts/check-i18n-parity.mjs` (`package.json:16`): gleiche Schlüssel, gleiche `{platzhalter}`, kein englischer Text in fremden Locales außer mit Ausnahmeliste

Die Standardvorlagen ziehen in diese Dateien um. Die Codes der Wartegründe werden im Frontend gespiegelt (`queue.waiting.*`), und zwar mit denselben Codes. Ein Test vergleicht die beiden Code-Mengen.

## 6. Aufteilung in PRs

1. **Sprache und Standardvorlagen:** Helfer, `en.json` und `de.json`, Auflösung über `notification_language`, Standardvorlagen pro Sprache beim Rendern, Feld in der UI, Paritätstest. *Risiko:* Der Textvergleich schlägt bei Zeilen fehl, die alte Migrationen leicht verändert haben. Dagegen helfen Tests mit den heutigen Vorgaben.
2. **Wartegründe als Code plus Parameter:** `waiting_parts` im Speicher und in der API, Rendern der Benachrichtigung in der Zielsprache, Frontend mit Rückfall auf den englischen Text. Ohne Migration. *Risiko:* Code und englischer Text laufen auseinander. Dagegen hilft ein Test, der aus dem Code den englischen Satz erzeugt und mit `waiting_reason` vergleicht. Kollisionen mit #3615 und #3641 sind möglich, beide ändern `print_scheduler.py`.
3. **Hilfstexte:** Dauer, ETA, „Unknown“, Tasten, Digest, Abbruchgründe. *Risiko:* gering, aber diese Texte sind über viele Stellen verstreut.
4. **Sprache pro Anbieter (optional):** Spalte und Migration, Auswahl im Anbieter-Dialog. *Risiko:* Die Migration muss auf SQLite und Postgres laufen.
5. **Übersetzungen:** die übrigen 14 Sprachen, nach Möglichkeit in einzelnen Beiträgen. *Risiko:* Qualität. Muttersprachler sollten gegenlesen.

## 7. Abstimmung

- **Mit dashu33, vor jeder Zeile Code:** fragen, ob schon etwas begonnen wurde und welchen Umfang er plant. Anbieten, PR 2 (Codes im Scheduler) zu übernehmen, weil das eng an #3587, #3615 und #3641 hängt. Er könnte PR 1 und PR 5 machen. Die Abweichung zu `notification_language` und die korrigierte Zahl (ca. 180 statt 150) offen nennen.
- **#3641:** Die neuen Variablen `{printer}` und `{filament}`, der Farbpunkt und die Discord-Felder gibt es nur bei unveränderten Vorlagen. Genau dort greift auch die Prüfung aus Abschnitt 3, also nutzen beide Funktionen dieselbe Prüfung. Die Feldnamen (Printer, Job, Slot …), „Any {model}“ und die Farbfamilien müssen mit übersetzt werden. Erst #3641 mergen, dann darauf aufbauen.
- **#3642 (Satz zum Fehlbestand):** Der Satz entsteht als neuer englischer Text im Wartegrund. Er sollte gleich als Code mit Parametern angelegt werden, etwa `filament_short` mit `{needed_g, available_g}`, sonst muss er später ein zweites Mal umgebaut werden.
