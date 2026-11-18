# Übergabe an die lokale Claude-Code-Sitzung: #3612 Etikettendruck am echten Brother QL-820NWB

Du arbeitest auf dem Windows-PC des Nutzers und erreichst den Druckserver per SSH (HP EliteDesk, Ubuntu 24.04, LAN `192.168.1.115`, Tailnet `100.112.171.42`, Bambuddy unter `/opt/bambuddy`). Sprich Deutsch mit dem Nutzer. Code, Commits und Texte für GitHub sind englisch. Verbindlich ist `CLAUDE.md` auf dem Branch `farm` von `balin77/bambuddy`, Abschnitte 1, 1a, 2, 4 und 5.

**Nichts an `maziggy/*` posten:** kein PR, kein Issue, kein Kommentar. #3612 ist noch nicht zugewiesen, und der Nutzer gibt selbst frei.

## Stand

- **Feature:** Spulen-Etiketten direkt auf einem Brother-QL-Netzwerkdrucker drucken (Issue maziggy/bambuddy#3612).
  - Branch `feature/label-direct-print`, von `upstream/dev`.
  - Commits: `1c4e4742` (Feature), `654fdee2` (Changelog), `f4333bb9` (Schrift-Fallback für das Testetikett).
- **farm:** Cherry-Picks `61f18fff` und `c605c7ce`. CI ist grün, das Image `ghcr.io/balin77/bambuddy:farm` ist gebaut (Farm-Build `c605c7ce`).
- **Umsetzung:** eigene Umsetzung des Brother-Rasterprotokolls über TCP 9100, keine neue Abhängigkeit.
  - Der Byte-Strom ist identisch mit `brother_ql`, mit einer Ausnahme: Der Druckerstatus wird vor dem Auftrag gelesen.
  - Getestet ist das nur gegen einen simulierten Drucker. **Am echten Gerät ist noch nichts getestet. Das ist deine Aufgabe.**
- **Drucker:** QL-820NWB, 300 dpi, im LAN, Endlosband DK-22223 (50 mm).

## 1. Server aktualisieren

1. Per SSH auf den Server und nach `/opt/bambuddy`.
2. `farm/update-bambuddy.sh` ausführen. Das Skript sichert die Daten, zieht das Image, startet neu und prüft den Healthcheck.
   - Den In-App-Update-Button nicht benutzen.
   - **Niemals `docker compose down -v`.**
3. In der Bambuddy-Oberfläche prüfen, dass die Version auf den Farm-Build `c605c7ce` zeigt (Suffix `+farm.…`).

## 2. Drucker vorbereiten

1. Den QL-820NWB ins LAN bringen und ihm eine feste IP geben (DHCP-Reservierung im Router). Der Raw-Port 9100 ist ab Werk aktiv.
2. Vom Server aus prüfen, ob der Port erreichbar ist: `nc -vz <drucker-ip> 9100`, oder mit `bash -c '</dev/tcp/<ip>/9100'`.
3. DK-22223 (50 mm Endlos) einlegen und den Deckel schliessen.

## 3. Einrichten und Testdruck

1. Settings → Filament → Karte **Label printer** öffnen:
   - Typ: **Brother QL (network)**
   - Adresse: die feste IP
   - Modell: **QL-820NWB**
   - Band: **50 mm continuous (DK-22223)**
2. **Test print** drücken. Erwartet:
   - Ein kurzes Etikett mit Rahmen, „Bambuddy test label“, Modell, Band und Datum.
   - Darunter in der Karte: „Printer answered: 50 mm continuous tape“.
3. Mit dem Nutzer festhalten:
   - **a) Status über TCP:** Antwortet der Drucker? Steht „Printer answered: …“ da, oder nur „Test label sent“ ohne Antwort? Davon hängt ab, ob „falsches Band“ und „Deckel offen“ erkannt werden.
   - **b) Lesbarkeit:** Ist der Text aufrecht und lesbar, also nicht gespiegelt? Läuft er entlang des Bands?
   - **c) Zentrierung:** Sitzt das Etikett mittig auf dem 50-mm-Band, ohne abgeschnittenen Rand?
   - **d) Schnitt und Länge:** Wird nach dem Etikett geschnitten? Wie lang ist das Stück? Erwartet sind 400 Punkte, also etwa 34 mm, plus Vorschubrand.

## 4. Erstes echtes Etikett

1. Inventar → eine Spule anhaken → **Print labels…**.
2. Format **Roll (label printer tape)**, Band 50 mm, Länge 40 mm. Die Vorschau ist schwarzweiss.
3. **Print on label printer** drücken. Erwartet:
   - Der Dialog schliesst.
   - Eine Meldung „Printing 1 label…“ erscheint, danach „Printed 1 label“.
   - Das Etikett sieht aus wie die Vorschau. Den QR-Code mit dem Handy scannen: Er muss die Spule in Bambuddy öffnen.
4. **Mehrere Etiketten:** 3 Spulen anhaken und drucken.
   - Prüfen: Kommen alle 3 heraus, jedes einzeln geschnitten?
   - Prüfen: Meldet Bambuddy erst nach dem dritten „Printed 3 labels“?
5. **Länge:** einmal mit 80 mm Länge drucken und das Stück nachmessen.
6. **Auto-Druck:** „Add spool“ öffnen. Die Checkbox „Print label after saving“ muss sichtbar sein. Anhaken, eine Spule anlegen, und das Etikett muss kommen. Danach beim Nutzer nachfragen, ob die Spule wieder gelöscht werden soll.

## 5. Fehlerfälle (nur soweit der Drucker Status meldet, siehe 3a)

| Test | Erwartete Meldung |
|---|---|
| Deckel offen, dann drucken | „Label printer reports: cover open“, es wird nichts gedruckt |
| In den Einstellungen 62 mm wählen, 50 mm eingelegt lassen, Test print | Hinweis auf falsches Band (409), es wird nichts gedruckt |
| Drucker ausschalten, dann drucken | „Label printer not reachable“. Kein Hängen: Nach etwa 5 s kommt die Fehlermeldung |
| Band leer oder nicht eingelegt | „no media“ bzw. „end of media“ |

Danach die Einstellungen wieder korrekt setzen.

## 6. Wenn etwas nicht stimmt

- **Text verkehrt herum oder gespiegelt:** In `backend/app/api/routes/labels.py` die Konstante `TAPE_ROTATION` drehen (ROTATE_90 ↔ ROTATE_270). Das betrifft alle Druckaufträge. Das Testetikett dreht sich in `brother_ql.py` `_test_image` selbst, also beide prüfen.
- **Etikett verschoben oder abgeschnitten:** Die Bandtabelle steht in `backend/app/services/label_printers/brother_ql_media.py`. Beim 50-mm-Band sind es 554 Punkte und 12 Nadeln linker Rand.
- **Nur das erste von mehreren Etiketten kommt, oder Bambuddy meldet „did not confirm all labels“:** Den Status-Mitschnitt aufzeichnen, siehe unten. Die Abschlusslogik steht in `brother_ql.py` `send()` und zählt pro Seite eine „completed“-Meldung.
- **Keine Statusantwort:** Das ist kein Fehler, der Druck läuft trotzdem. Es entfallen nur die Vorab-Prüfungen. Für die PR-Notiz festhalten.
- **Status-Mitschnitt** (vom Server aus, nur lesend):

  ```bash
  python3 - <<'PY'
  import socket
  s = socket.create_connection(("<drucker-ip>", 9100), 5)
  s.sendall(b"\x00" * 400 + b"\x1b@" + b"\x1biS")
  s.settimeout(3)
  print(s.recv(64).hex(" "))
  PY
  ```

  Erwartet sind 32 Bytes, die mit `80 20 42` beginnen. Byte 10 ist die Bandbreite in mm (0x32 = 50), Byte 11 der Medientyp (0x0A = Endlos). Die Ausgabe in den Bericht übernehmen.
- **Logs:** `docker compose logs --since 10m bambuddy | grep -i label`

**Code-Korrekturen:**
1. Auf dem Branch `feature/label-direct-print` arbeiten, nicht auf `farm`.
2. Pro Korrektur einen kleinen Commit, mit Test (der Fake-Drucker steht in `backend/tests/unit/test_brother_ql_3612.py`).
3. Den Branch pushen und die CI per `workflow_dispatch` (`ci.yml`) starten.
4. Danach per `git cherry-pick -x` auf `farm` übernehmen und pushen. Das Image baut dann automatisch.
5. Changelog-Commits nicht auf farm übernehmen.

## 7. Ergebnis

Bericht an den Nutzer auf Deutsch:
- Antworten auf 3a bis 3d.
- Ergebnisse aus Abschnitt 4 und 5: Was ging, was nicht.
- Fotos der Etiketten, falls der Nutzer welche macht.
- Status-Mitschnitt.
- Gemachte Korrekturen mit Commits.

Danach in `farm/drafts/PR-3612.md`:
- unter „Testing“ den Punkt „Tested with my printer model“ abhaken: QL-820NWB, Firmware-Version, DK-22223;
- unter „Additional Notes“ die Erkenntnisse ergänzen, z. B. ob der Status über TCP kommt.

Committen und auf `farm` pushen. Den PR selbst stellt erst der Nutzer nach seiner Freigabe.
