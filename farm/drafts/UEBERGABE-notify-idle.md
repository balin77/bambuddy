# Übergabe an die lokale Claude-Code-Sitzung: „Printer idle: waiting for filament“ (#3725) testen

Du arbeitest auf dem Windows-PC des Nutzers. Den Druckserver erreichst du per SSH:
- HP EliteDesk, Ubuntu 24.04;
- LAN `192.168.1.115`, Tailnet `100.112.171.42`;
- Bambuddy unter `/opt/bambuddy`, im LAN unter `http://192.168.1.115:8000`.

Sprich Deutsch mit dem Nutzer. Code, Commits und Texte für GitHub sind englisch.

Verbindlich ist `CLAUDE.md` auf `farm` von `balin77/bambuddy`, Abschnitte 1, 1a, 2, 4 und 5. Besonders gilt:
- **Keine AI-Kennzeichnung.**
  - Autor ist `Raphael <gublerra@gmail.com>`.
  - Kein `Co-Authored-By`, kein `Claude-Session`, kein „Generated with Claude Code“, keine claude.ai-Links.
  - Vor jedem Push muss `git log origin/farm..HEAD --format='%an %ae %cn %ce%n%B' | grep -i -E "claude|anthropic"` leer sein.
- **Offene PR-Branches nicht umschreiben:** kein Rebase, kein Force-Push, nur neue Commits obendrauf.
- **An `maziggy/*` postest du nichts.** PRs stellt nur der Nutzer.

## Stand

| Issue | Branch | Auf farm | Entwürfe |
|---|---|---|---|
| **#3725** Drucker steht wegen Filament; knappe Spule sofort | `feature/notify-idle-waiting-for-filament` (enthält #3641 und #3642) | ja, mit To-do-Satz (Anpassungs-Commit „farm: idle-for-filament uses the To do holds …“) | `PR-3725.md`, `WIKI-3725.md`, Bilder `pr-assets/3725/` |

**Was gebaut ist:**
- Neues Ereignis „Printer idle: waiting for filament“, eigene Checkbox je Kanal (Standard an, neue Spalte `on_printer_idle_for_filament`).
- Es kommt, wenn ein Drucker 5 Minuten leer steht und alle wartenden Aufträge für ihn Filament brauchen. Einmal pro Stillstand; wieder nur, wenn der Drucker zwischendurch gedruckt hat oder sich die zu ladenden Filamente ändern.
- Eine knappe Spule meldet „Queue Job Waiting“ sofort, einmal pro Auftrag, mit dem To-do-Satz („Not enough PLA Lava Red on P1S right: A3 has 196 g, the job needs 505 g“).
- Der Zustand liegt in der Tabelle `settings` (Schlüssel `queue_filament_idle_watch`), also bleibt er nach einem Neustart erhalten.
- Ausgenommen: Plate Clear offen, Plate Changer leer, Sensorsperre, Trocknen, Druck läuft, offline.

Bisher nur automatisch getestet. **Der Test auf der Farm ist deine Aufgabe.**

## 1. Server aktualisieren

1. Per SSH nach `/opt/bambuddy` und `farm/update-bambuddy.sh` ausführen.
   - Den Update-Knopf in der App nicht benutzen.
   - **Niemals `docker compose down -v`.**
2. Vorher prüfen, dass das Image `ghcr.io/balin77/bambuddy:farm` gebaut ist.
3. Die Migration ergänzt nur eine Spalte; das Backup des Skripts abwarten.

## 2. Testschritte

Settings → Notifications: Beim Discord-Kanal ist **Printer idle: waiting for filament** angehakt (Standard). Vorlagen unverändert. „Loaded filament first“ ist an.

1. **Stillstand:** Einen Auftrag anlegen, der ein nicht geladenes Filament braucht, und den Drucker 5 Minuten leer stehen lassen. Erwartet: **eine** Discord-Nachricht „Printer idle: waiting for filament“ mit den Feldern Printer, Load und Jobs.
2. **Kein Wiederholen:** Tür öffnen und schliessen, weitere Minuten warten. Erwartet: keine zweite Nachricht.
3. **Dazwischen gedruckt:** Einen anderen Auftrag drucken lassen, danach wieder 5 Minuten leer. Erwartet: wieder eine Nachricht.
4. **Anderes Filament:** Den Auftrag auf ein anderes fehlendes Filament ändern. Erwartet: neue Nachricht.
5. **Knappe Spule:** Auftrag für einen Drucker mit zu wenig Gramm. Erwartet: sofort „Queue Job Waiting“ mit „Not enough … A3 has … g, the job needs … g“, einmal. Eine Nachricht „Printer idle“ folgt frühestens nach 5 Minuten.
6. **Neustart:** Container neu starten (`farm/update-bambuddy.sh` oder `docker compose restart bambuddy`, nie `down -v`), während der Stillstand besteht. Erwartet: keine Wiederholung.
7. **Geänderte Vorlage:** Die Vorlage des Ereignisses um ein Wort ändern. Erwartet: die Nachricht kommt im alten Format ohne Felder. Danach „Reset“.
8. **Checkbox:** Beim Anbieter ausschalten, Stillstand erzeugen. Erwartet: keine Nachricht. Wieder einschalten.
9. **Ausnahmen:** Plate Changer leer oder Plate Clear offen: keine Nachricht „Printer idle“.

Die echten Discord-Screenshots macht der Nutzer am Handy (erfundene Namen). Sie ersetzen die Bilder in `pr-assets/3725/`; danach `PR-3725.md` unter „Testing“ anpassen.

## 3. Wenn etwas nicht stimmt

- **Logs:** `docker compose logs --since 10m bambuddy`
- **Korrekturen:** Auf `feature/notify-idle-waiting-for-filament` neue Commits (Raphael, ohne AI-Zeilen, mit Test), pushen, per `git cherry-pick -x` auf farm (ohne Changelog-Commit). Vor jedem farm-Push `git fetch`; lokale, ungepushte Commits obendrauf setzen.
- **Unbeständige Tests:** `EmbeddedCameraContext.test.tsx` scheitert gelegentlich in der CI ohne Bezug; Job neu starten.

## 4. Ergebnis

Bericht an den Nutzer auf Deutsch: je Testpunkt ok oder Fehler, Korrekturen mit Commits, offene Fragen. Den Praxistest in `PR-3725.md` eintragen, committen, `git fetch`, auf farm pushen.

**PRs stellt erst der Nutzer.** #3725 erst nach #3641 und #3642 und nach der Zuweisung des Issues.
