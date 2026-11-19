# Übergabe an die lokale Claude-Code-Sitzung: #3615 und #3619 auf der Farm testen

Du arbeitest auf dem Windows-PC des Nutzers und erreichst den Druckserver per SSH (HP EliteDesk, Ubuntu 24.04, LAN `192.168.1.115`, Tailnet `100.112.171.42`, Bambuddy unter `/opt/bambuddy`). Sprich Deutsch mit dem Nutzer. Code, Commits und Texte für GitHub sind englisch. Verbindlich ist `CLAUDE.md` auf dem Branch `farm` von `balin77/bambuddy`, Abschnitte 1, 1a, 2, 4 und 5.

**Nichts an `maziggy/*` posten:** kein PR, kein Issue, kein Kommentar. #3615 und #3619 sind offen und nicht zugewiesen. Der Nutzer gibt selbst frei.

## Stand

- **#3615 „To do“-Liste der Warteschlange**
  - Branch `feature/queue-todo-list`, Commits `f6fd4a91a` (Feature) und `9b30b242e` (Changelog).
  - Auf `farm`: `267ac48a5`, `6685e67e4`, `41fa73323`, `0ada8e79f` und `94328c659`.
  - Die farm-Erweiterung bringt den Eintrag „Plattenwechsler leer“ (#3575), die Priorität aus #3587 und den Lagerhinweis aus #3590.
- **#3619 Spule anlegen**
  - Inhalt: letzte Werte, Farben der Marke, Leerspulen der Marke zuerst.
  - Branch `feature/spool-form-last-used`, Commits `3d64b4285`, `31f664d34`, `fd593c35c`, `b62944433`, `794038aab` und `ba847100b` (Changelog).
  - Auf `farm`: `07ba7c5a1`, `0bd00a956`, `c088452f8`, `dc6d5f0e2` und `c84cf0a43`.
- **farm-HEAD:** `8d782b3be`. CI ist grün, das Image `ghcr.io/balin77/bambuddy:farm` ist gebaut.
- **Entwürfe:** `farm/drafts/PR-3615.md`, `WIKI-3615.md`, `PR-3619.md`, `WIKI-3619.md`.
- **Screenshots:** auf dem Branch `pr-assets` unter `3615/` und `3619/`.
- Getestet ist bisher nur mit automatischen Tests und Screenshots mit nachgebildeter API. **Der Test an der echten Farm ist deine Aufgabe.**

## 1. Server aktualisieren

1. Per SSH auf den Server und nach `/opt/bambuddy`.
2. `farm/update-bambuddy.sh` ausführen. Das Skript macht ein Backup, zieht das Image, startet neu und prüft den Healthcheck.
   - Den In-App-Update-Button nicht benutzen.
   - **Niemals `docker compose down -v`.**
3. In der Oberfläche prüfen, dass der Farm-Build `8d782b3be` oder neuer läuft.

## 2. Test #3615: To-do-Liste

Die Liste ist aus dem Zustand abgeleitet, nicht gespeichert. Ein Eintrag erscheint nur, solange ein Auftrag wartet, und verschwindet von selbst, wenn sein Grund weg ist.

1. **Leere Liste:** Keine Aufträge warten. Dann ist in der Navigation kein Zähler-Symbol zu sehen und oben auf der Queue-Seite keine Liste.
2. **Druckbett freigeben:**
   - Einen Druck beenden lassen, sodass der Drucker auf die Plattenbestätigung wartet. Einen weiteren Auftrag für diesen Drucker in die Queue legen.
   - Erwartet: Unter dem Drucker steht „Confirm the plate is clear“ mit dem Knopf **Plate is clear**.
   - Knopf drücken. Der Eintrag verschwindet, der Auftrag startet.
3. **Filament laden:**
   - Einen Auftrag mit erzwungener Farbe (Force color match) anlegen, die kein Drucker geladen hat. Dazu im Druckdialog die Checkbox „Show inventory colours“ einschalten und eine Lagerfarbe wählen.
   - Erwartet: ein Eintrag „Load filament“ mit Farbname. Aufträge ohne festen Drucker stehen unter „Any <Modell>“ mit „on <Drucker> or <Drucker>“.
   - Zwei solche Aufträge mit derselben Farbe müssen **einen** Eintrag mit beiden Auftragsnamen ergeben.
   - Ist die Farbe im Lager aufgebraucht, steht dort „none left in inventory“. Ist „Loaded filament first“ (#3587) eingeschaltet, erscheint die Priorität („priority in N h“ / „has priority“).
4. **Bereitgestellter Auftrag:** Ein Auftrag mit „Require manual start“ zeigt den Eintrag „Start the staged job“ mit **Start**. Fehlt Filament, muss die Rückfrage „Print anyway“ erscheinen wie auf der Queue-Seite.
5. **Plattenwechsler leer (#3575):** Bei einem Drucker mit Plattenzähler den Zähler auf 0 setzen und einen Auftrag für ihn anlegen. Erwartet: ein Eintrag mit **Refilled**.
6. **Offline / Smart Plug:** Wenn möglich einen Drucker mit Smart Plug testen, der nicht einschalten kann, etwa wenn der Plug selbst aus ist. Erwartet: „Printer did not power on“.
7. **Handy:**
   - Das Zähler-Symbol oben antippen. Die Liste öffnet sich als Blatt von unten, ohne seitliches Scrollen.
   - Ein Link „Open printer“ springt zur Druckerkarte.
8. **Rechte, falls Benutzer eingerichtet sind:** Ein Benutzer ohne Recht auf einen Drucker darf dessen Einträge nicht sehen.

Festhalten: Was ging, was nicht, was verwirrend war. Wenn möglich Screenshots, aber ohne echte Namen in Bildern für GitHub.

## 3. Test #3619: Spule anlegen

1. **Letzte Werte:**
   - Eine Spule anlegen: Marke Polymaker, Material PLA, Leerspule „PolyTerra PLA - Cardboard“, Lagerort, Preis pro kg, Slicer-Preset.
   - Danach erneut **Add Spool** öffnen. Erwartet:
     - Oben steht „Started with your last spool (Polymaker PLA) · Clear“.
     - Marke, Material, Preset, Gewichte, Lagerort, Preis und Kategorie sind übernommen.
     - Farbe und Notiz sind leer.
   - **Clear** leert alles.
   - Bearbeiten und Kopieren müssen unverändert funktionieren.
   - Hinweis für den Nutzer: Das Gedächtnis gilt pro Browser und Gerät, das Handy merkt sich also getrennt. Safari löscht es nach 7 Tagen ohne Besuch. Ausgenommen ist die App auf dem Home-Bildschirm.
2. **Farben der Marke:**
   - Marke Polymaker und Material PLA: In der Farbauswahl müssen die PolyTerra-PLA-Farben erscheinen. Vorher kam dort nichts.
   - Marke „PolyTerra“ zeigt dieselben Farben.
   - **Show all colors** zeigt alle Farben der Marke.
3. **Leerspulen:** Bei Marke Polymaker stehen im Gewichtswähler unter **Suggested** die PolyMaker-Einträge und „PolyTerra PLA - Cardboard“, alles andere unter **All**.
4. **Zusammenspiel mit #3612:** Ist der Etikettendrucker eingerichtet, muss „Print label after saving“ weiter funktionieren, auch mit übernommenen Werten.
5. **Profile Defaults (#1326):** Wird bei einem anderen Material ein gespeicherter Profile Default gefunden, muss sein Preset greifen. Ein selbst gewähltes Preset darf nicht überschrieben werden.

## 4. Wenn etwas nicht stimmt

- **Logs:** `docker compose logs --since 10m bambuddy`
- **Code-Korrekturen:**
  1. Auf dem jeweiligen Feature-Branch arbeiten (`feature/queue-todo-list` bzw. `feature/spool-form-last-used`), nicht auf `farm`.
  2. Kleine Commits, mit Test. Prüfungen: ruff, basedpyright, ESLint, tsc, knip, `npm run check:i18n`, Vitest, pytest.
  3. Branch pushen, dann `ci.yml` per `workflow_dispatch` starten.
  4. Per `git cherry-pick -x` auf `farm` übernehmen. Changelog-Commits nicht.
  5. Vor dem Push auf `farm` erst `git fetch` und die Commits obendrauf setzen. Auf `farm` arbeiten auch Cloud-Sitzungen.
- **Bekannte Grenzen, kein Fehler:**
  - **#3615:**
    - Ein gemerkter Filament-Eintrag eines bereitgestellten Auftrags wird nicht neu geprüft, solange der Auftrag bereitgestellt bleibt.
    - Druckerfehler (HMS) sind nicht in der Liste.
  - **#3619:**
    - Die Verknüpfung zum Spoolman-Filament wird nicht gemerkt, weil die Farbe dazugehört.
    - Lieferanten werden nur übernommen, wenn Bambuddy für die neue Spule keine eigenen Lieferanten geerbt hat.

## 5. Ergebnis

Bericht an den Nutzer auf Deutsch:
- je Testpunkt: ok / Fehler (mit Beschreibung);
- gemachte Korrekturen mit Commits;
- offene Fragen.

Danach in `farm/drafts/PR-3615.md` und `PR-3619.md` unter „Testing“ den Praxistest abhaken (Druckermodell, Firmware) und Erkenntnisse unter „Additional Notes“ ergänzen. Committen und auf `farm` pushen, vorher `git fetch`. Die PRs selbst stellt erst der Nutzer nach der Zuweisung und seiner Freigabe.
