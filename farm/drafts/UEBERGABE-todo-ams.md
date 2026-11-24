# Übergabe an die lokale Claude-Code-Sitzung: To-do-Liste mit AMS-Bild (#3726) testen

Du arbeitest auf dem Windows-PC des Nutzers. Den Druckserver erreichst du per SSH:
- HP EliteDesk, Ubuntu 24.04;
- LAN `192.168.1.115`, Tailnet `100.112.171.42`;
- Bambuddy unter `/opt/bambuddy`, im LAN unter `http://192.168.1.115:8000`.

Sprich Deutsch mit dem Nutzer. Code, Commits und Texte für GitHub sind englisch.

Verbindlich ist `CLAUDE.md` auf `farm` von `balin77/bambuddy`, Abschnitte 1, 1a, 2, 4 und 5. Besonders gilt:
- **Keine AI-Kennzeichnung.**
  - Autor ist `Raphael <gublerra@gmail.com>`.
  - Kein `Co-Authored-By`, kein `Claude-Session`, kein „Generated with Claude Code“, keine claude.ai-Links.
  - Vor jedem Push muss `git log upstream/dev..HEAD --format='%an %ae %cn %ce%n%B' | grep -i -E "claude|anthropic"` leer sein.
- **Offene PR-Branches nicht umschreiben:** kein Rebase, kein Force-Push, nur neue Commits obendrauf.
- **An `maziggy/*` postest du nur, was der Nutzer ausdrücklich freigibt.** Zeig ihm jeden Text vorher.
- Der Branch `pr-assets` wird nie gelöscht oder per Force-Push überschrieben.

## Stand

| Issue | Branch | CI | Auf farm | Entwürfe |
|---|---|---|---|---|
| **#3726** Schritt 1: AMS-Bild und Spule in der To-do-Liste zuweisen | `feature/queue-todo-ams-picture` (von `feature/queue-todo-prepare`) | grün | ja, mit den feinen Rechten und der Ausblend-Option | `PR-3726.md`, `WIKI-3726.md`, Bilder `pr-assets/3726/` |
| **#3726** Schritt 2: Stecker wieder an, Auftrag bearbeiten/verschieben, Spule anlegen | `feature/queue-todo-actions-in-place` (auf Schritt 1) | grün | ja | `PR-3726-step2.md` |
| Resume/Stop eines pausierten Drucks | nur auf farm (hängt an #3648) | – | ja | im Schritt-2-Entwurf erwähnt |

Abhängigkeiten: Schritt 1 setzt #3622 (To-do-Liste), #3634 (Slot-Hinweise) und #3640 (Prepare-Zeilen) voraus. Die PRs für #3726 stellt **nur der Nutzer**, erst nachdem diese drei gemerged sind.

**Was gebaut ist:**
- **AMS-Bild:** Ein „Load filament“-Eintrag zeigt die Slots des Druckers als Karten. Darüber steht, im selben Rahmen, jedes zu ladende Filament genau über seinem Slot, mit Pfeil. Zustände: raus (gelb), leer (gestrichelt), passt, gesperrt (läuft gerade), unbekannt.
- **Weitere Einheiten** (AMS B, HT, extern) sind eingeklappt („Show AMS-B“). AMS 3H bricht bei 5 Spalten um. Bei „Any P1S“ gibt es Knöpfe zum Umschalten zwischen den Druckern.
- **Zuweisen im Eintrag:** „Assign spool for A3“ zeigt die passenden Lagerspulen im Eintrag. Dazu „Scan label“, „Add new spool“, „Set up slot“. Nach dem Zuweisen aktualisiert sich die Liste.
- **Schritt 2:** „Switch on again“ (Stecker), „Edit job“ und „Move to another printer“ (nur für fest zugeordnete Aufträge) bei fehlendem Filament, „Add spool“ wenn nichts im Lager ist.
- **Nur farm:** „Resume“ und „Stop“ bei pausiertem Druck. Stop fragt immer nach, mit demselben Dialog wie die Druckerkarte.
- **Rechte (farm):** Assign/Scan `inventory:update`, Add spool `inventory:create`, Set up slot `printers:filament`, Switch on again `smart_plugs:control`, Edit/Move die Warteschlangen-Rechte (eigene oder alle), Resume `printers:pause_resume`, Stop `printers:stop`. Ohne Recht ist der Knopf grau mit Hinweis, mit der Gruppen-Option „Hide controls this group cannot use“ (#3639) verschwindet er.

Bisher ist das nur automatisch und mit Bildern gegen eine nachgebildete API geprüft. **Der Test auf der Farm ist deine Aufgabe.**

## 1. Server aktualisieren

1. Per SSH nach `/opt/bambuddy` und `farm/update-bambuddy.sh` ausführen.
   - Den Update-Knopf in der App nicht benutzen (es gibt keinen).
   - **Niemals `docker compose down -v`.**
2. Vorher prüfen, dass das Image `ghcr.io/balin77/bambuddy:farm` gebaut ist.
3. Danach muss der aktuelle farm-HEAD laufen. Es gibt keine Migration für #3726.

## 2. Tests je Fall

Öffne die To-do-Liste (Queue-Seite oder das Panel). Teste jeden Fall am PC **und am Handy (390 px Breite)**. Erwartet immer: genau **ein** Bild je Eintrag, die zu ladende Karte genau über ihrem Slot, kein seitliches Scrollen.

1. **Knappe Spule ersetzen:** Auftrag für einen festen Drucker, dessen Spule zu wenig Gramm hat. Erwartet: Titel „Replace spool“, der Slot ist gelb mit „… g · out“, darüber die neue Karte „new, at least … g“ und ein Pfeil.
2. **Mehrere Filamente / mehrere AMS:** Auftrag mit zwei fehlenden Farben an einem Drucker mit zwei AMS. Erwartet: Beide Karten über ihren Slots, das zweite AMS eingeklappt, falls nichts hineingeht; ein Slot des laufenden Drucks ist gesperrt (Schloss) und wird nie angeboten.
3. **Modell-Auftrag („Any P1S“):** Erwartet: ein Bild für den wahrscheinlich nächsten Drucker („likely next“), die Knöpfe darüber wechseln das Bild. Das Bild **darf sich nicht vervielfachen** (nur eins, auch nach Minuten).
4. **Zuweisen im Eintrag, mit RFID und ohne:**
   - „Assign spool for A3“ öffnet die Liste im Eintrag; passende Spulen mit genug Gramm stehen oben, zu knappe grau mit Hinweis.
   - Spule antippen und „Assign“. Erwartet: Toast, die Liste aktualisiert sich, der Hinweis „Put the new spool in first, then assign it.“ erscheint, solange noch die alte Spule im Slot ist.
   - Bei einer **Bambu-RFID-Spule** erkennt der Drucker die Spule selbst; bei einer **Spule ohne RFID** zusätzlich „Set up slot A3“ (Typ und Farbe setzen) prüfen.
   - **Spoolman**, falls im Einsatz: Zuweisen geht über Spoolman; ist Spoolman nicht erreichbar, gibt es keinen Assign-Knopf; „Add new spool“ fehlt.
5. **Etikett scannen:** „Scan label“ im Eintrag, Spulen-QR scannen. Erwartet: Zuweisung in denselben Slot; „Back“ führt zurück zur Liste.
6. **Neue Spule anlegen:** „Add new spool“ im Eintrag; das Formular öffnet sich über dem Panel. Escape schließt erst das Formular, nicht das Panel.
7. **Slot einrichten:** „Set up slot A3“ bei einem Slot ohne RFID; Typ und Farbe setzen, Liste prüfen.
8. **Stecker wieder an:** Drucker mit Smart-Plug, der nicht eingeschaltet hat. „Switch on again“. Erwartet: Toast „Switch-on command sent“; ohne Stecker eine Fehlermeldung.
9. **Auftrag bearbeiten / verschieben:** Bei einem Eintrag mit fehlendem Filament „Edit job“ (Farbe ändern) und bei einem festen Auftrag „Move to another printer“. Erwartet: Der Bearbeiten-Dialog der Queue öffnet sich über dem Panel. Bei „Any …“-Aufträgen gibt es kein Move.
10. **Spule anlegen bei leerem Lager:** Filament, das nirgends im Lager ist („none left in inventory“): „Add spool“ öffnet das Formular mit Typ und Farbe vorbelegt.
11. **Pausierter Druck:** Druck pausieren (z. B. Filament leer). „Resume“ setzt fort. „Stop“ fragt immer nach; „Cancel“ tut nichts, bestätigen stoppt. Danach aktualisieren sich Liste und Druckerstatus.
12. **Print anyway, Plate Clear, Plate Changer, gestarteter Auftrag:** weiter wie vorher, auch mit Bild.
13. **Rechte mit eingeschränkter Gruppe:** Konto einer Gruppe mit nur wenigen Rechten (z. B. nur Pause/Resume und Clear Plate).
    - Option „Hide controls this group cannot use“ **aus:** Die Knöpfe sind grau mit Hinweis (z. B. „You do not have permission to assign spools“).
    - Option **an:** Die nicht erlaubten Knöpfe fehlen ganz; erlaubte bleiben. Das Bild bleibt in beiden Fällen sichtbar.
    - Server prüft weiter: Eine gesperrte Aktion lehnt auch die API ab.

## 3. Wenn etwas nicht stimmt

- **Logs:** `docker compose logs --since 10m bambuddy`
- **Korrekturen:**
  1. Auf dem jeweiligen Branch (`feature/queue-todo-ams-picture` bzw. `…-actions-in-place`) arbeiten: neue Commits, als Raphael, ohne AI-Zeilen, mit Test.
  2. Pushen und `ci.yml` per `workflow_dispatch` starten.
  3. Per `git cherry-pick -x` auf farm übernehmen, ohne Changelog-Commits; Konflikte mit den feinen Rechten, `usePermissionGate` und den pausierten Einträgen behalten beide Seiten.
  4. Vor jedem farm-Push `git fetch` ausführen und die eigenen Commits obendrauf setzen.
- **Unbeständige Tests:** `EmbeddedCameraContext.test.tsx` und gelegentlich ein Test der Druckerseite scheitern in der CI ohne Bezug zu uns. Dann den Job neu starten.

## 4. Ergebnis

Bericht an den Nutzer auf Deutsch: je Testpunkt ok oder Fehler, Korrekturen mit Commits, offene Fragen. Den Praxistest in `PR-3726.md` und `PR-3726-step2.md` unter „Testing“ eintragen (derzeit „nicht an echten Druckern getestet“), committen, `git fetch`, auf farm pushen.

**PRs stellt erst der Nutzer**, nachdem #3622, #3634 und #3640 gemerged sind: zuerst Schritt 1, dann Schritt 2. Resume/Stop kommen erst nach dem Merge von #3648 in einen eigenen Folge-PR.
