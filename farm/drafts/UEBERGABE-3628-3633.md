# Übergabe an die lokale Claude-Code-Sitzung: #3628 und #3633 auf der Farm testen

Du arbeitest auf dem Windows-PC des Nutzers und erreichst den Druckserver per SSH (HP EliteDesk, Ubuntu 24.04, LAN `192.168.1.115`, Tailnet `100.112.171.42`, Bambuddy unter `/opt/bambuddy`). Sprich Deutsch mit dem Nutzer. Code, Commits und Texte für GitHub sind englisch.

Verbindlich ist `CLAUDE.md` auf `farm` von `balin77/bambuddy`, Abschnitte 1, 1a, 2, 4 und 5. Dazu gelten diese Regeln:

- **Keine AI-Kennzeichnung**, weder in Commits noch in Entwürfen.
  - Autor `Raphael <gublerra@gmail.com>`.
  - Kein `Co-Authored-By`, kein `Claude-Session`, kein „Generated with Claude Code“.
  - Vor jedem Push muss `git log upstream/dev..HEAD --format='%an %ae %cn %ce%n%B' | grep -i -E "claude|anthropic"` leer sein.
- **Nichts an `maziggy/*` posten:** kein PR, kein Issue, kein Kommentar. Das gilt, solange der Nutzer nicht ausdrücklich freigibt.
- **Offene PR-Branches nicht umschreiben:** kein Rebase, kein Force-Push, nur neue Commits obendrauf. Das betrifft vor allem `feature/spool-form-last-used` (PR #3626).

## Stand

- **#3628 Versionen im Dateimanager als eine Karte.** Das Issue ist offen und nicht zugewiesen.
  - Branch `feature/variant-group-card`, die CI ist grün.
  - Auf `farm` liegen `3496a8c71` bis `59518e80c` und die Anpassung `78623e671`.
  - **Das Backend ist berührt:**
    - `GET /library/files?with_variant_members=true` ist neu und optional.
    - Die Rechte der Versionsgruppen sind strenger. Man sieht nur Mitglieder, die man lesen darf. Ändern darf eine Gruppe nur, wer alle aktiven Mitglieder besitzt oder „update all“ hat.
  - Keine Migration.
- **#3633 Katalogfarben nach Farbe oder Name.** Das Issue ist offen und nicht zugewiesen.
  - Branch `feature/spool-form-color-order`, abgezweigt von `feature/spool-form-last-used`. Der PR folgt erst, wenn #3626 gemergt ist. Die CI ist grün.
  - Auf `farm` liegt `71f42fc01`. Es ist nur Frontend.
- **farm-HEAD:** `006a3c95d` oder neuer. Das Image `ghcr.io/balin77/bambuddy:farm` wird automatisch gebaut. Prüfe erst, dass der Build fertig ist.
- **Entwürfe** in `farm/drafts/`: `PR-3628.md`, `WIKI-3628.md`, `PR-3633.md`, `WIKI-3633.md`.
- **Screenshots** auf `pr-assets` unter `3628/` und `3633/`.
- Getestet ist bisher nur automatisch und mit Screenshots gegen eine nachgebildete API. **Der Test an der echten Farm ist deine Aufgabe.**

## 1. Server aktualisieren

1. Per SSH nach `/opt/bambuddy`.
2. `farm/update-bambuddy.sh` ausführen.
   - Nicht den Update-Knopf in der App benutzen.
   - **Niemals `docker compose down -v`.**
3. In der Oberfläche prüfen, dass `006a3c95d` oder neuer läuft.

## 2. Test #3628: Versionsgruppen im Dateimanager

**Vorbereitung:**
- Im Dateimanager zwei bis drei geslicte Dateien desselben Modells für verschiedene Druckermodelle auswählen, zum Beispiel X1C und P1S.
- Mit **Group as versions** gruppieren.
- Eine Version davon in einen anderen Ordner verschieben.

1. **Drei Ansichten:** Kacheln, Liste und Spalten.
   - Die Gruppe erscheint als **eine** Karte bzw. Zeile. Darauf stehen das Vorschaubild der ersten Version, die Druckermodelle und „N versions“.
   - Aufklappen zeigt jede Version mit Laufzeit, Gewicht und ⋮-Menü. Die Version im anderen Ordner trägt den Hinweis „in <Ordner>“.
   - **Kacheln:** Eine aufgeklappte Gruppe nimmt eine ganze Zeile ein. Die normalen Karten bleiben gleich hoch.
   - **Spalten:** Die Gruppe anklicken. Mit → oder Enter geht sie auf, mit ← wieder zu.
2. **Menü pro Version:** Preview, Print, Download, „Remove from group“.
3. **Menü der Gruppe:**
   - **Print** öffnet **einen** Auftrag, der alle Versionen als Druckeralternativen enthält. Die Queue wählt dann den passenden Drucker.
   - **Ungroup** löst die Gruppe auf.
   - **Delete all versions** fragt nach. Liegt eine Version in einem anderen Ordner, nennt die Rückfrage das.
   - **Ungroup und Delete all erst ganz am Schluss testen**, oder mit einer Testgruppe.
4. **Auswahl:**
   - Das Häkchen auf der Karte markiert nur die Versionen **in diesem Ordner**.
   - Mit **Select all**, dann Move oder Delete darf nichts aus einem anderen Ordner betroffen sein.
   - Eine markierte Gruppe plus zwei einzelne Dateien ergibt den Knopf „Print (1 group + 2 files)“.
5. **Plattenfreigabe (#3576, nur farm):** In einer Gruppe bei einer Version „Clears plate“ setzen. Beim Druck der Gruppe muss die Druckeralternative den Haken übernehmen.
6. **Rechte, falls Benutzer eingerichtet sind:**
   - Ein Mitarbeiter mit „Library: read own / update own“ sieht in einer Gruppe nur seine eigenen Dateien. Liegt nur eine davon sichtbar vor, erscheint sie als normale Datei.
   - Liegen in der Gruppe auch fremde Dateien, sind Ungroup und Remove gesperrt. Der Server antwortet dann 403. **Das ist gewollt.**
   - Ein Admin kann alles.
7. **Handy:** Mit 390 px Breite darf in keiner Ansicht seitlich gescrollt werden müssen.

## 3. Test #3633: Katalogfarben sortieren

1. **Add Spool** öffnen, Marke **Polymaker**, Material **PLA**, dann den Reiter **Color & Cost**.
2. Neben den Katalogfarben stehen zwei kleine Knöpfe: **A–Z** und **Farbkreis**. Standard ist A–Z, die Reihenfolge ist also wie bisher.
3. **Farbkreis:** Die Reihenfolge geht von Rot über Orange, Gelb, Grün, Cyan, Blau, Violett und Pink zu Braun. Danach folgen Weiss, Grau und Schwarz, Clear steht zuletzt.
   - Eine echte Spule in die Hand nehmen und ihre Farbe suchen. Geht das schneller?
4. **Gemerkt:** Das Formular schliessen und neu öffnen, die Wahl bleibt. Auf einem anderen Gerät gilt wieder A–Z, das ist gewollt.
5. **Show all colors:** Die Farben des gewählten Materials bleiben vorne, die übrigen folgen. Jeder Teil ist für sich sortiert.
6. **Suche** im Farbfeld: Die Treffer folgen der gewählten Reihenfolge.
7. **SpoolBuddy:** Auf der Seite **Write Tag** gibt es dieselben Knöpfe. Sie müssen aufs Display passen.
8. **Bekannt, kein Fehler:** Sehr helle Töne wie Pastellrosa sortiert das Formular zu Weiss. Das Inventar macht es genauso.

## 4. Wenn etwas nicht stimmt

- **Logs:** `docker compose logs --since 10m bambuddy`
- **Korrekturen:**
  1. Auf dem Feature-Branch arbeiten: `feature/variant-group-card` bzw. `feature/spool-form-color-order`. Als Raphael, ohne AI-Zeilen, mit Test.
  2. Prüfungen: ruff, basedpyright, ESLint, tsc, knip, `npm run check:i18n`, Vitest, pytest.
  3. Den Branch pushen, dann `ci.yml` per `workflow_dispatch` starten.
  4. Per `git cherry-pick -x` auf `farm` übernehmen. Changelog-Commits nicht übernehmen.
  5. Vor dem Push `git fetch` ausführen und die eigenen Commits obendrauf setzen. Auch Cloud-Sitzungen pushen auf `farm`.
- **Auf farm anders als upstream:**
  - farm hat die Plattenfreigabe pro Alternative (#3576).
  - Die Option `dismissible` des Bestätigungsdialogs ist nachgerüstet (`78623e671`).
- **Unbeständiger Test:** `EmbeddedCameraContext.test.tsx` scheitert in der CI gelegentlich. Er hat mit diesen Features nichts zu tun, ein erneuter Lauf ist grün.

## 5. Ergebnis

Bericht an den Nutzer auf Deutsch:
- je Testpunkt: ok oder Fehler, mit Beschreibung;
- gemachte Korrekturen mit Commits;
- offene Fragen.

Danach in `farm/drafts/PR-3628.md` und `PR-3633.md` unter „Testing“ den Praxistest eintragen (Druckermodell, Firmware) und die Punkte „Not yet checked on the real server“ ersetzen. Committen, `git fetch`, auf `farm` pushen.

Die PRs stellt erst der Nutzer:
- **#3628** nach der Zuweisung.
- **#3633** nach der Zuweisung **und** nach dem Merge von #3626.
