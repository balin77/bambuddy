# Übergabe an die lokale Claude-Code-Sitzung: #3659 auf dem Server testen

Du arbeitest auf dem Windows-PC des Nutzers. Den Druckserver erreichst du per SSH:
- HP EliteDesk, Ubuntu 24.04;
- LAN `192.168.1.115`, Tailnet `100.112.171.42`;
- Bambuddy unter `/opt/bambuddy`, im LAN unter `http://192.168.1.115:8000`.

Sprich Deutsch mit dem Nutzer. Code, Commits und Texte für GitHub sind englisch.

Verbindlich ist `CLAUDE.md` auf `farm` von `balin77/bambuddy`, Abschnitte 1, 1a, 2, 4 und 5. Besonders gilt:
- **Keine AI-Kennzeichnung.** Autor ist `Raphael <gublerra@gmail.com>`, kein `Co-Authored-By`, kein `Claude-Session`, keine claude.ai-Links.
- **An `maziggy/*` postest du nur, was der Nutzer ausdrücklich freigibt.**

## Stand (farm-HEAD e50e7ff05 oder neuer)

**#3659:** maziggy hat es am 22.11. selbst behoben (`3a38447a6`). Auf farm: `16d05bd0f` (sein Commit), `e56746908` (Anpassung ohne #3522), `e50e7ff05` (nur farm: Knopf in der To-do-Liste).

- **Warteschlange:** Wartet ein Auftrag nur wegen einer zu knappen Spule (Loaded filament first), zeigt die Zeile **Print anyway** (statt Start). Die Bestätigung nennt bei „Any <Modell>“ jeden knappen Drucker mit Slot und Gramm.
- **To-do-Liste (nur farm):** Der Eintrag „Not enough …“ hat je Auftrag **Print anyway**, nur wenn der Auftrag nur wegen knapper Spulen wartet (nicht bereitgestellt, keine Farbe fehlt ganz) und der Nutzer starten darf.

## 1. Server aktualisieren

1. Per SSH nach `/opt/bambuddy`, dann `farm/update-bambuddy.sh` ausführen. Den Update-Knopf der App nicht benutzen. **Niemals `docker compose down -v`.**
2. Vorher prüfen, dass das Image `ghcr.io/balin77/bambuddy:farm` gebaut ist; danach muss e50e7ff05 oder neuer laufen.

## 2. Test

Voraussetzung: Settings → Queue & Dispatch → **Loaded filament first** an.

1. Einen Auftrag „Any P1S“ anlegen, der mehr PLA Lava Red braucht, als die Spule im P1S hat. Erwartet:
   - Die Zeile in der Warteschlange zeigt **Print anyway**, nicht Start.
   - Ein Klick öffnet die Bestätigung. Sie listet **jeden knappen P1S** mit Slot und Gramm (`Druckername: …`).
   - **Abbrechen** ändert nichts: der Auftrag wartet weiter.
   - **Bestätigen:** der Auftrag geht auf den ersten freien P1S mit dem Filament.
2. Dasselbe mit einem Auftrag auf einen **fest gewählten** Drucker.
3. Ein Auftrag, dem eine Farbe **ganz fehlt**, zeigt **kein** Print anyway (Zeile und To-do-Liste).
4. To-do-Liste (Glocke/Queue-Seite): Der Eintrag „Not enough …“ zeigt dieselbe Aktion je Auftrag, gleiche Bestätigung. Nach dem Bestätigen verschwindet der Eintrag nach dem Neuladen.
5. Den Auftrag auf einen anderen Drucker verschieben: die Überschreibung fällt weg, der Auftrag wartet wieder normal.
6. Ein Nutzer ohne Startrecht sieht das Print anyway in der To-do-Liste nicht.
7. Auf dem Handy (schmale Breite): kein seitliches Scrollen.

Ergebnisse dem Nutzer berichten und in `farm/drafts/PR-3659.md` unter „Test results“ eintragen.
