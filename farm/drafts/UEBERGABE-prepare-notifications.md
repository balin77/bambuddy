# Übergabe an die lokale Claude-Code-Sitzung: Issues posten, „Prepare“ fertigstellen, Server testen

Du arbeitest auf dem Windows-PC des Nutzers. Den Druckserver erreichst du per SSH:
- HP EliteDesk, Ubuntu 24.04;
- LAN `192.168.1.115`, Tailnet `100.112.171.42`;
- Bambuddy liegt unter `/opt/bambuddy`.

Sprich Deutsch mit dem Nutzer. Code, Commits und alle Texte für GitHub sind englisch.

Verbindlich ist `CLAUDE.md` auf `farm` von `balin77/bambuddy`, Abschnitte 1, 1a, 2, 4 und 5. Besonders gilt:
- **Keine AI-Kennzeichnung**, nirgends:
  - Autor ist `Raphael <gublerra@gmail.com>`.
  - Kein `Co-Authored-By`, kein `Claude-Session`, kein „Generated with Claude Code“, keine Links auf claude.ai.
  - Vor jedem Push muss `git log upstream/dev..HEAD --format='%an %ae %cn %ce%n%B' | grep -i -E "claude|anthropic"` leer sein.
- **Offene PR-Branches nicht umschreiben.** Kein Rebase, kein Force-Push, nur neue Commits obendrauf. Das gilt für `feature/queue-todo-list` (PR #3622), `feature/spool-form-last-used` (PR #3626) und jeden anderen Branch mit offenem PR.
- **An `maziggy/*` postest du nur, was der Nutzer ausdrücklich freigibt.** Zeig ihm jeden Text vor dem Posten und warte auf sein OK.

## Stand

- **#3628 Versionen als eine Karte:** Issue an balin77 zugewiesen, noch kein PR. Auf farm gibt es neu das Popover in der Kachelansicht bzw. ein Blatt von unten am Handy. Entwürfe: `PR-3628.md`, `WIKI-3628.md`.
- **#3633 Katalogfarben nach Farbe:** auf farm. Der PR folgt erst nach dem Merge von #3626.
- **#3634 Slot für fehlendes Filament:** auf farm. Der PR folgt erst nach dem Merge von #3622.
- **#3622 (#3615):** Neuer Commit `c96f05c2a` „Queue: the To do list leaves out printers with nothing to do“. Die CI ist grün, er ist auf farm als `07e94001c`.
- **„Prepare“ (Vorbereiten der nächsten Filamente):**
  - Das Issue ist noch nicht gepostet.
  - Der Code ist fertig, reviewt und getestet: 5 Commits auf `feature/queue-todo-prepare`, Basis `feature/queue-todo-replace-slot` (#3634).
  - **Er ist nur lokal in der Cloud-Sitzung, nicht gepusht.** Die Commits tragen den Platzhalter `#PREPARE`.
- **farm-HEAD:** `07e94001c` oder neuer.

## 1. Issues posten (nur mit Freigabe des Nutzers)

Lies vorher `.github/ISSUE_TEMPLATE/feature_request.yml` bzw. `bug_report.yml` in `maziggy/bambuddy` und übertrage die Abschnitte in die Felder der Vorlage. Suche vorher kurz nach Duplikaten. Die Entwürfe liegen auf farm unter `farm/drafts/`:

1. **„Prepare“** – `ISSUE-todo-prepare.md`. Titel: `[Feature]: To do list: prepare the filaments of a printer's next jobs, also while it prints`.
2. **Lesbare Benachrichtigungen** – `ISSUE-notification-format.md`, Teil **A**. Titel: `[Feature]: Readable notifications: printer, job and filament as separate fields, with a colour dot`.
3. **Bug `filament_short`** – dieselbe Datei, Teil **B**.
   - Vorher beim Nutzer erfragen: die Bambuddy-Version (Settings > About) und den zugeschnittenen Discord-Screenshot (KnittedPenguin … `filament_short`).
   - Den Screenshot mit erfundenen oder unkritischen Namen anhängen.
4. **Kommentar zu #2933** („Notification language localization“) – dieselbe Datei, Teil **C**. Das ist ein Kommentar, kein neues Issue.

Danach im jeweiligen Entwurf die Status-Zeile aktualisieren: „Posted on … as maziggy/bambuddy#NNNN“ bzw. die Kommentar-URL. Committen, `git fetch`, auf farm pushen.

**Optional, nur wenn der Nutzer es will:** In PR #3622 kurz kommentieren, was der neue Commit `c96f05c2a` behebt. Gemeint sind Druckerkarten ohne Eintrag, wenn ein fest zugewiesener Auftrag auf nichts wartet.

## 2. „Prepare“ fertigstellen (sobald die Issue-Nummer da ist)

Der Code liegt **nur in der Cloud-Sitzung**. Gib dem Nutzer die Nummer und diesen Satz zum Weiterleiten an die Cloud-Sitzung:

> „Das Prepare-Issue ist #NNNN. Ersetze `#PREPARE` in den Commits von `feature/queue-todo-prepare` durch `#NNNN`, pushe, starte die CI und übernimm es auf farm.“

Die Cloud-Sitzung erledigt dann:
- Rewording, Push und CI;
- Cherry-Pick auf farm ohne den Changelog-Commit;
- Entwürfe `PR-NNNN.md` und `WIKI-NNNN.md`;
- Screenshots auf `pr-assets/NNNN/`;
- die Zeile in CLAUDE.md 1a.

Lokal ist dafür nichts zu tun. Der PR selbst folgt erst nach dem Merge von #3622 und #3634 und nach der Zuweisung.

## 3. Server aktualisieren und testen

1. Per SSH nach `/opt/bambuddy`. `farm/update-bambuddy.sh` ausführen.
   - Den Update-Knopf in der App nicht benutzen.
   - **Niemals `docker compose down -v`.**
   - Prüfen, dass `07e94001c` oder neuer läuft.
2. Die Testpunkte aus `farm/drafts/UEBERGABE-3628-3633.md` abarbeiten, falls noch offen. Für #3628 gilt jetzt das Popover:
   - **Desktop:** „Show versions“ in der Kachelansicht öffnet ein Fenster unter der Kachel. Keine andere Kachel bewegt sich.
   - **Schliessen:** zweiter Klick, Klick daneben, Escape, Tab hinaus, Scrollen der Liste.
   - **Dialoge:** Details, Umbenennen, Löschen und Print aus dem ⋮-Menü einer Version schliessen das Fenster zuerst. Der Dialog liegt dann obenauf.
   - **Handy:** Es erscheint ein Blatt von unten mit ✕. Scrollen schliesst es nicht.
   - **Liste und Spalten** klappen wie bisher an Ort und Stelle auf.
3. **#3634 an echten Druckern**: To-do-Liste unter Queue.
   - **Freier Slot:** Ein Drucker wartet auf Filament und hat einen leeren Slot. Erwartet: „Free: A2“.
   - **Ersetzbarer Slot:** Alle Slots voll, ein Slot wird von keinem wartenden Auftrag gebraucht. Erwartet: „Can be replaced: A4 (PLA Green)“, mit demselben Farbnamen wie auf der Druckerkarte.
   - **Alle gebraucht:** Erwartet: „Every loaded filament is needed by a waiting job“.
   - **Laufender Druck:** Dessen Slots werden nie angeboten.
   - **„Any <Modell>“:** eine Zeile pro Drucker, höchstens 3, dann „+N more“.
   - Der Hinweis aktualisiert sich nach dem nächsten Scheduler-Durchlauf (etwa 30 s).
4. **#3622-Fix:** Ein Drucker, dessen fest zugewiesener Auftrag auf nichts wartet, zeigt keine leere Karte mehr.

## 4. Wenn etwas nicht stimmt

- **Logs:** `docker compose logs --since 10m bambuddy`
- **Korrekturen:**
  1. Auf dem jeweiligen Feature-Branch arbeiten, als Raphael, ohne AI-Zeilen, mit Test.
  2. Pushen, dann `ci.yml` per `workflow_dispatch` starten.
  3. Per `git cherry-pick -x` auf farm übernehmen, ohne Changelog-Commits.
  4. Vor jedem farm-Push `git fetch` und die eigenen Commits obendrauf setzen.
- **Unbeständiger Test:** `EmbeddedCameraContext.test.tsx` scheitert gelegentlich in der CI. Dann einfach neu starten.

## 5. Ergebnis

Bericht an den Nutzer auf Deutsch:
- gepostete Issues und Kommentare mit Nummern bzw. Links;
- je Testpunkt: ok oder Fehler;
- Korrekturen mit Commits;
- offene Fragen.

Den Praxistest in `PR-3628.md`, `PR-3633.md` und `PR-3634.md` unter „Testing“ eintragen. Committen, `git fetch`, auf farm pushen.
