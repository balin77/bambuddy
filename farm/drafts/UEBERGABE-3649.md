# Übergabe an die lokale Claude-Code-Sitzung: #3649 auf dem Server testen

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
- **Offene PR-Branches nicht umschreiben:** kein Rebase, kein Force-Push, nur neue Commits obendrauf. Das gilt vor allem für `feature/override-from-inventory` (PR #3618), auf dem #3649 aufbaut.
- **An `maziggy/*` postest du nur, was der Nutzer ausdrücklich freigibt.** Zeig ihm jeden Text vorher.

Falls die Übergabe `farm/drafts/UEBERGABE-3647-3648-3634.md` noch nicht abgearbeitet ist, mach sie zuerst. Sie teilt sich das Server-Update mit dieser hier.

## Stand (farm-HEAD `73329e67d` oder neuer)

**#3649 Lagerfarbe für einen fest gewählten Drucker:** Issue gepostet, nicht zugewiesen.
- **Branch:** `feature/inventory-filament-pinned-printer`, von `feature/override-from-inventory`. Der PR folgt erst nach dem Merge von #3618. Die CI ist grün.
- **Auf farm:** `88b8132bb` bis `50e227358`, dazu die Anpassung `9fa8e1010`. farm hat keine Filament-Sperre pro Gruppe (#3522), diese Teile sind entfernt. Neu zeigt die To-do-Liste „none left in inventory“ auch bei einem fest gewählten Drucker.
- **Entwürfe:** `PR-3649.md`, `WIKI-3649.md`. Screenshots liegen unter `pr-assets/3649/`.

**Was gebaut ist:**
- **Ein Drucker, Modus Warteschlange oder Planen:**
  - Im Slot-Dropdown jeder Farbe gibt es die Gruppe „From inventory (not loaded)“.
  - Nach einer Wahl zeigt die Zeile „Waits for filament“. Die übrigen Farben behalten ihren Slot.
- **Mehrere Drucker:** Ein eigenes Feld „From inventory (not loaded)“. Jeder gewählte Drucker wartet auf diese Farbe.
- **„ASAP“:** gesperrt, solange eine Lagerfarbe gewählt ist, mit Erklärung. Steckt die Farbe schon im Drucker, wird sie diesem Slot zugeordnet, und „ASAP“ bleibt frei.
- **Erzwungen:** Eine Lagerwahl ist immer erzwungen. Es gibt dort kein Häkchen „Force color match“.
- **Start:** Mit „Loaded filament first“ startet der Auftrag von selbst, sobald die Farbe eingelegt ist. Ohne diese Einstellung bleibt er bereitgestellt, und man drückt **Start**. Der Dialog sagt das.
- **Bestand:**
  - Ist die Farbe im Lager aufgebraucht, steht im Wartetext „– none left in inventory“.
  - Das Ereignis „Filament Out of Stock“ kommt einmal pro Engpass, nicht nach jedem weiteren Druck.

Bisher ist das nur automatisch und mit Screenshots gegen eine nachgebildete API geprüft. **Der Test am echten A1 Mini ist deine Aufgabe.**

## 1. Server aktualisieren

1. Per SSH nach `/opt/bambuddy`, dann `farm/update-bambuddy.sh` ausführen.
   - Den Update-Knopf in der App nicht benutzen.
   - **Niemals `docker compose down -v`.**
2. Vorher prüfen, dass das Image `ghcr.io/balin77/bambuddy:farm` gebaut ist.
3. Danach muss `73329e67d` oder neuer laufen.
4. „Show inventory colours“ muss eingeschaltet sein (Druckdialog oder Settings → Queue & Dispatch, aus #3590).

## 2. Test #3649 am A1 Mini

1. **Ein Drucker:**
   - Eine Datei mit zwei Farben drucken. Als Drucker den A1 Mini wählen, als Modus **Queue**.
   - Unter „Filamentzuordnung“ das Dropdown einer Farbe öffnen. Unter den geladenen Slots steht die Gruppe „From inventory (not loaded)“, mit Bestandswarnung wie bei #3590.
   - Eine Lagerfarbe wählen, die **nicht** geladen ist. Erwartet:
     - Die Zeile zeigt „Waits for filament“ samt Hinweis.
     - Die andere Farbe behält ihren Slot.
     - Die Kosten sind als Teilschätzung markiert.
     - „ASAP“ ist gesperrt, mit Erklärung.
2. **Auftrag in die Warteschlange:**
   - Der Auftrag wartet. In der To-do-Liste steht „Load filament“ mit Slot-Hinweis.
   - Ist „Loaded filament first“ eingeschaltet, steht „Waiting for filament: …“ in der Queue. Ist die Einstellung aus, ist der Auftrag bereitgestellt („needs PLA …“).
3. **Farbe einlegen:**
   - Die Spule im Lager dem Slot zuweisen bzw. die passende Spule einlegen.
   - Mit „Loaded filament first“ startet der Auftrag von selbst. Ohne die Einstellung auf **Start** drücken.
   - Nach dem Start prüfen: Die andere Farbe kam aus dem ursprünglich gewählten Slot.
4. **Bearbeiten:** Einen wartenden Auftrag öffnen. Die Lagerwahl ist wieder zu sehen, und Speichern behält sie.
5. **„ASAP“-Gegenprobe:** Eine Lagerfarbe wählen, die doch im A1 Mini steckt. Sie wird dem Slot zugeordnet, und „ASAP“ bleibt frei.
6. **Mehrere Drucker:** Zwei Drucker ankreuzen, Modus Queue.
   - Das Feld „From inventory (not loaded)“ erscheint.
   - Eine Farbe wählen: Beide Aufträge warten auf diese Farbe auf ihrem eigenen Drucker.
7. **Bestand null:**
   - Eine Lagerfarbe mit Bestand 0 wählen.
   - Der Wartetext endet auf „– none left in inventory“, und die To-do-Liste zeigt den Lagerhinweis.
   - Die Benachrichtigung „Filament Out of Stock“ (falls eingerichtet) kommt **einmal**, auch wenn der Drucker inzwischen andere Aufträge druckt.
8. **Handy (390 px):** Das Dropdown und das Feld laufen nicht über.
9. **Gegenprobe ohne Lagerwahl:** Ein normaler Auftrag verhält sich wie vorher.

## 3. Wenn etwas nicht stimmt

- **Logs:** `docker compose logs --since 10m bambuddy`
- **Korrekturen:**
  1. Auf `feature/inventory-filament-pinned-printer` arbeiten: neue Commits, als Raphael, ohne AI-Zeilen, mit Test.
  2. Pushen und `ci.yml` per `workflow_dispatch` starten.
  3. Per `git cherry-pick -x` auf farm übernehmen, ohne Changelog-Commits.
  4. farm hat die Filament-Sperre #3522 nicht, also diese Teile weglassen.
  5. Vor jedem farm-Push `git fetch` ausführen und die eigenen Commits obendrauf setzen.
- **Unbeständiger Test:** `EmbeddedCameraContext.test.tsx` scheitert gelegentlich in der CI. Dann den Lauf neu starten.

## 4. Ergebnis

Bericht an den Nutzer auf Deutsch:
- je Testpunkt: ok oder Fehler;
- Korrekturen mit Commits;
- offene Fragen.

Den Praxistest in `farm/drafts/PR-3649.md` unter „Testing“ eintragen: Drucker A1 Mini, Firmware, was am echten Gerät geprüft wurde. Committen, `git fetch`, auf farm pushen.

Den PR stellt erst der Nutzer, und zwar erst nach dem Merge von #3618 und der Zuweisung von #3649.
