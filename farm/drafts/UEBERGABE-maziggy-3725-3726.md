# Übergabe an die lokale Claude-Code-Sitzung: Punkte von maziggy zu #3725 und #3726 auf der Farm testen

Du arbeitest auf dem Windows-PC des Nutzers. Den Druckserver erreichst du per SSH:
- HP EliteDesk, Ubuntu 24.04;
- LAN `192.168.1.115`, Tailnet `100.112.171.42`;
- Bambuddy unter `/opt/bambuddy`, im LAN unter `http://192.168.1.115:8000`.

Sprich Deutsch mit dem Nutzer. Code, Commits und Texte für GitHub sind englisch.

Verbindlich ist `CLAUDE.md` auf `farm` von `balin77/bambuddy`, Abschnitte 1, 1a, 2, 4 und 5. Besonders gilt:
- **Keine AI-Kennzeichnung.**
  - Autor ist `Raphael <gublerra@gmail.com>`.
  - Kein `Co-Authored-By`, kein `Claude-Session`, kein „Generated with Claude Code“, keine claude.ai-Links, keine Erwähnung einer KI in Commits oder Entwürfen.
  - Vor jedem Push muss `git log origin/farm..HEAD --format='%an %ae %cn %ce%n%B' | grep -i -E "claude|anthropic"` leer sein (Ausnahme: ein Betreff, der die Datei CLAUDE.md nennt).
- **Niemals `docker compose down -v`.**
- **Kein Update-Knopf in der App.** Der Server wird mit `farm/update-bambuddy.sh` aktualisiert.
- **Gepushte Historie nie umschreiben:** kein Rebase gepushter Commits, kein Force-Push; `pr-assets` nie löschen oder force-pushen.
- **An `maziggy/*` postest du nichts.** PRs stellt nur der Nutzer, und erst nachdem #3622 und #3641 gemergt sind (Reihenfolge: #3622, #3641, #3725, dann #3726 in zwei Schritten).

## Stand

maziggy hat #3725 und #3726 am 25.11.2026 dem Nutzer zugewiesen und Rückfragen gestellt. Die Antworten stehen in den Entwürfen im Abschnitt „Maintainer's points“.

| Issue | Branch | CI | Auf farm | Entwürfe |
|---|---|---|---|---|
| **#3725** Drucker steht wegen Filament; auch ein ausgeschalteter Drucker | `feature/notify-idle-waiting-for-filament` (enthält #3641 und #3642) | siehe GitHub Actions des Branches | ja, `6cee735bc` (To-do-Holds) | `PR-3725.md` (mit „Rebuild after #3622 and #3641“), `WIKI-3725.md` |
| **#3726** Schritt 1: AMS-Bild, Spule im Eintrag zuweisen | `feature/queue-todo-ams-picture` | siehe GitHub Actions des Branches | ja, bis `c68867180` | `PR-3726.md`, `WIKI-3726.md`, Bilder `pr-assets/3726/` |
| **#3726** Schritt 2: Aktionen im Eintrag | `feature/queue-todo-actions-in-place` | siehe GitHub Actions des Branches | ja, bis `7b99cdb18` (Stecker braucht `smart_plugs:read` und `control`, Test der Druckerbereiche) | `PR-3726-step2.md` |

Den genauen farm-Stand zeigt `git log origin/farm -15`; die letzten Commits sind „farm: drafts for maziggy's points on #3725 and #3726“ und „farm: CLAUDE.md notes maziggy's order for #3725 and #3726“.

**Was neu ist:**
- #3725: Ein Drucker, den die Abschaltautomatik (Smart Plug `auto_on`) ausgeschaltet hat, zählt als untätig, wenn der Stecker zuletzt AUS war, letzte bekannte AMS-Slots vorliegen, keine Plate Clear offen ist, keine fehlgeschlagene Wake-Wartezeit läuft und kein wartender Auftrag den Drucker einschalten würde. Das Ereignis kommt nur mit „Loaded filament first“. Für einen „Any model“-Auftrag kommt eine Nachricht je untätigem Drucker (gewollt).
- #3726: Drucker ohne AMS zeigt die externe Spule als einzigen Slot; die Farbkreise sind die der Druckerkarte (Mehrfarben, durchscheinend, keine Nummer im Kreis); Stop eines pausierten Drucks fragt nach; Nutzer mit eingeschränkter Gruppe sehen nur ihre Drucker.

Bisher nur automatisch getestet, Bilder gegen eine Mock-API. **Der Test auf der Farm ist deine Aufgabe.**

## 1. Server aktualisieren

1. Per SSH nach `/opt/bambuddy` und `farm/update-bambuddy.sh` ausführen. Vorher prüfen, dass das Image `ghcr.io/balin77/bambuddy:farm` gebaut ist.
2. Das Backup des Skripts abwarten. Es gibt keine neue Migration in diesem Stand außer der Spalte aus #3725 (hat die Farm schon).

## 2. Testschritte

**(a) Ausgeschalteter Drucker (#3725).** Settings → Notifications: „Printer idle: waiting for filament“ ist beim Discord-Kanal an, Vorlagen unverändert, „Loaded filament first“ an.
1. Einen Auftrag für einen Drucker anlegen, dessen Filament dieser nicht geladen hat; der Drucker wird von der Abschaltautomatik / dem Smart Plug ausgeschaltet. Erwartet: nach 5 Minuten **eine** Nachricht „Printer idle: waiting for filament“, danach keine Wiederholung.
2. „Loaded filament first“ ausschalten. Erwartet: keine solche Nachricht mehr. Wieder einschalten.
3. Ein Drucker, der nur getrennt ist (Stecker AN, z. B. Netzwerkkabel ziehen). Erwartet: keine Nachricht.
4. Ein wartender Auftrag, dessen Filament passt. Erwartet: der Drucker wird eingeschaltet, keine Nachricht.

**(b) A1 Mini ohne AMS (#3726).** Auftrag mit einem fehlenden Filament für den A1 Mini. Erwartet: der To-do-Eintrag zeigt die externe Spule als einzigen Slot, die neue Spule steht darüber, „Assign“ funktioniert.

**(c) Farbkreise (#3726).** Erwartet: gleiche Optik wie auf der Druckerkarte; eine Mehrfarben-Spule zeigt ihre Farben; eine durchscheinende oder klare Spule scheint durch; keine Nummer im Kreis.

**(d) Stop (#3726).** Einen Druck pausieren, im To-do-Eintrag „Stop“ drücken. Erwartet: dieselbe Rückfrage wie auf der Druckerkarte („Stop Print“, Text mit Druckernamen, roter Knopf); erst nach Bestätigung wird gestoppt.

**(e) Eingeschränkte Gruppe (#3726).** Mit einem Nutzer, dessen Gruppe nur einige Drucker darf: die To-do-Liste zeigt nur diese Drucker; „Switch on again“ erscheint nur mit `smart_plugs:read` und `smart_plugs:control` (sonst ausgegraut oder, mit der Ausblend-Option, weg).

Spoolman-Modus ist bisher nur durch Tests abgedeckt; wenn Spoolman an ist, Zuweisen kurz prüfen.

## 3. Wenn etwas nicht stimmt

- **Logs:** `docker compose logs --since 10m bambuddy`
- **Korrekturen:** Auf dem jeweiligen Branch neue Commits (Raphael, ohne AI-Zeilen, mit Test), pushen, dann per `git cherry-pick -x` auf farm (ohne Changelog-Commit). Vor jedem farm-Push `git fetch origin farm`; nur lokale, ungepushte Commits rebasen. Farm-spezifische Anpassungen als Commit „farm: … (#NNNN)“.
- **Unbeständige Tests:** `EmbeddedCameraContext.test.tsx` und der NextPause-Test in `PrintersPage` scheitern gelegentlich ohne Bezug; einzeln wiederholen.

## 4. Ergebnis

Bericht an den Nutzer auf Deutsch: je Testpunkt ok oder Fehler, Korrekturen mit Commits, offene Fragen. Den Praxistest unter „Testing“ in `PR-3725.md`, `PR-3726.md` und `PR-3726-step2.md` eintragen (ehrlich: was auf echten Druckern lief, was nicht), committen, `git fetch`, auf farm pushen.

**PRs stellt erst der Nutzer**, nach dem Merge von #3622 und #3641, dann #3725, dann #3726 Schritt 1 und danach Schritt 2. Für #3725 wird später ein neuer Branch aus `upstream/dev` gebaut („Rebuild after #3622 and #3641“ in `PR-3725.md`).
