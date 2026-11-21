# Übergabe an die lokale Claude-Code-Sitzung: Benachrichtigungen (#3642, #3641) und #3639 testen

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

## Stand (farm-HEAD `f0aa9517f` oder neuer)

| Issue | Branch (von `upstream/dev`) | CI | Auf farm | Entwürfe |
|---|---|---|---|---|
| **#3642** `filament_short` in der Benachrichtigung (Bug, balin77 zugewiesen) | `fix/notification-filament-short` | grün | ja, mit farm-Satz | `PR-3642.md` |
| **#3641** lesbare Benachrichtigungen (balin77 zugewiesen) | `feature/notification-readable` | grün | ja | `PR-3641.md`, `WIKI-3641.md`, Bilder `pr-assets/3641/` |
| **#2933** Sprache der Benachrichtigungen (dashu33 zugewiesen) | – | – | – | nur Plan `PLAN-notification-language.md` |
| **#3639** nicht erlaubte Bedienelemente ausblenden (nicht zugewiesen) | `feature/hide-unpermitted-controls` | grün | ja, mit den feinen Rechten aus #3248 | `PR-3639.md`, `WIKI-3639.md`, Screenshots `pr-assets/3639/` |

**Ausserdem:** Auf dem offenen PR-Branch `feature/variant-group-card` (PR #3643) behebt der neue Commit `f91948e68` zwei Fehler der Typprüfung. Er ist auch auf farm. Prüf, ob dessen CI grün ist.

**Was gebaut ist:**
- **#3642:** Statt `filament_short` steht ein Satz. Auf farm heisst er wie in der To-do-Liste, zum Beispiel „Not enough PLA Lava Red on Workshop: A2 has 12 g, the job needs 40 g“. Mit AMS-Backup steht „A2 + A3 have 25 g“. Ist der Typ unbekannt, steht „Filament“.
- **#3641:**
  - **Neue Variablen:** `{printer}` (bei Modell-Aufträgen „Any P1S“), `{filament}`, `{filament_type}`, `{color_name}`, `{color_hex}`, `{color_emoji}`, `{slot}`. Bei Plate Clear kommt `{job_name}` dazu.
  - **Discord:** Bei **unveränderter Standardvorlage** bekommt die Nachricht die Felder Printer, Job und Waiting for bzw. Finished bzw. Out of stock. Bei genau einem Filament ist die Seitenfarbe die Filamentfarbe.
  - **Geänderte Vorlage:** Die Nachricht bleibt genau wie vorher, also gleicher Text, grün und ohne Felder.
  - **Unverändert:** Die Standardtexte selbst, es gibt keine Migration.
  - **Farbpunkte:** 🔴🟠🟡🟢🔵🟣🩷🟤⚪⚫. Mehrfarbige Spulen bekommen 🌈, Clear-Filament ⚪ mit dem Zusatz „clear“.
  - **Nur auf farm:** Auch Filament Out of Stock und Plate Changer Empty haben die Felder. Bei Out of Stock bleibt `{filament}` der alte Text.
- **#3639:**
  - Neue Gruppen-Option „Hide controls this group cannot use“, standardmässig aus. Sie steht zuunterst in der Rechteliste.
  - Sie gilt nur, wenn **alle** Gruppen eines Benutzers sie haben, und nie für Admins.
  - Bedienelemente, die nur wegen eines fehlenden Rechts gesperrt sind, verschwinden. Aus einem anderen Grund gesperrte (offline, Druck läuft) bleiben grau.
  - Leere Abschnitte verschwinden ganz. Anzeigen bleiben.
  - Auf farm gilt die Option pro feinem Recht aus #3248.

Bisher ist das nur automatisch und mit Bildern gegen eine nachgebildete API geprüft. **Der Test auf der Farm ist deine Aufgabe.**

## 1. Server aktualisieren

1. Per SSH nach `/opt/bambuddy` und `farm/update-bambuddy.sh` ausführen.
   - Den Update-Knopf in der App nicht benutzen.
   - **Niemals `docker compose down -v`.**
2. Vorher prüfen, dass das Image `ghcr.io/balin77/bambuddy:farm` gebaut ist.
3. Danach muss `f0aa9517f` oder neuer laufen. Die Migration für #3639 ergänzt nur eine Spalte. Zur Sicherheit vorher das Backup des Skripts abwarten.

## 2. Test #3642 und #3641 (Discord)

Settings → Notifications: Der Discord-Kanal muss die Ereignisse **Queue Job Waiting**, **Plate Clear Required**, **Filament Low** und **Filament Out of Stock** gewählt haben. Die Vorlagen bleiben unverändert.

1. **Knappe Spule (#3642):**
   - Einen Auftrag für einen festen Drucker anlegen, dessen passende Spule laut Lager zu wenig Gramm hat.
   - Erwartet:
     - Titel „Queue Job Waiting“.
     - Die Beschreibung enthält „Not enough PLA … on <Drucker>: A2 has … g, the job needs … g“, und nirgends steht `filament_short`.
     - Darunter stehen die Felder **Printer**, **Job** und **Waiting for** mit Farbpunkt.
2. **Fehlende Farbe, Modell-Auftrag:**
   - Ein Auftrag für „Any P1S“ mit erzwungener Farbe, die nirgends geladen ist.
   - Erwartet: Das Feld Printer zeigt „Any P1S“, Waiting for zeigt z. B. „🟣 PLA Lavender Purple (#B39DDB)“, und die Seitenfarbe ist violett.
3. **Plate Clear Required:** Einen Druck beenden lassen. Erwartet: die Felder Printer und **Finished** mit dem Namen des Drucks.
4. **Filament Low:** Erwartet: der Farbpunkt der Spule und die Seitenfarbe der Spule.
5. **Gegenprobe mit geänderter Vorlage:**
   - Eine Vorlage leicht ändern, z. B. ein Wort im Text.
   - Erwartet: Diese Nachricht kommt wie früher, grün und ohne Felder. Danach die Vorlage mit „Reset“ zurücksetzen.
6. **Andere Kanäle** (falls eingerichtet, z. B. Telegram oder ntfy): Der Text ist wie vorher. Die neuen Variablen kann man in eigene Vorlagen einbauen.
7. **Screenshots:** Die echten Discord-Screenshots für den PR macht der Nutzer am Handy. Erfundene oder unkritische Namen verwenden. Die Bilder kommen nach `pr-assets/3641/`, als Ersatz für die Mock-Bilder. Danach `PR-3641.md` anpassen.

## 3. Test #3639 (Helfer-Gruppe)

1. Settings → Authentifizierung → Gruppen: Bei der Helfer-Gruppe zuunterst **Hide controls this group cannot use** einschalten. Diese Gruppe hat z. B. nur Pause/Resume und Clear Plate.
2. Mit dem Konto des Helfers am Handy und am PC die Druckerseite öffnen. Erwartet:
   - Pause ist sichtbar.
   - Stop, Licht, Achsen, Temperatur-Bedienung, Trocknen, Kamera, Dateien und Drucken sind **weg**, nicht ausgegraut.
   - Temperaturen, Fortschritt und AMS-Inhalt sind weiter zu sehen.
   - Keine leeren Rahmen, keine verwaisten Linien, kein seitliches Scrollen.
3. **Plate Clear** ist sichtbar. Ohne Recht Clear Plate ist „Platten nachfüllen“ weg, die Zahl der Platten bleibt.
4. **Offline-Drucker:** Seine erlaubten Knöpfe bleiben grau sichtbar.
5. **Gegenprobe:**
   - Option aus: alles wie vorher, ausgegraut.
   - Benutzer in zwei Gruppen, eine davon ohne Option: Er sieht die normale Ansicht.
   - Ein Admin sieht immer alles.
6. Der Server prüft die Rechte weiter. Eine gesperrte Aktion lehnt er auch per API ab.

## 4. Wenn etwas nicht stimmt

- **Logs:** `docker compose logs --since 10m bambuddy`
- **Korrekturen:**
  1. Auf dem jeweiligen Branch arbeiten: neue Commits, als Raphael, ohne AI-Zeilen, mit Test.
  2. Pushen und `ci.yml` per `workflow_dispatch` starten.
  3. Per `git cherry-pick -x` auf farm übernehmen, ohne Changelog-Commits.
  4. Vor jedem farm-Push `git fetch` ausführen und die eigenen Commits obendrauf setzen.
- **Ein Test muss angepasst werden:** #3642 und #3641 ändern dieselbe Stelle im Scheduler. Der Text kollidiert nicht, aber nach dem Merge des einen PR muss im anderen eine Testerwartung (`filament_short`) angepasst werden. Steht im PR-Entwurf.
- **Unbeständige Tests:** `EmbeddedCameraContext.test.tsx` und gelegentlich ein Test der Druckerseite scheitern in der CI ohne Bezug zu uns. Auch eine Zeitüberschreitung der Frontend-Tests nach 10 Minuten kommt vor. Dann den Job neu starten.

## 5. Ergebnis

Bericht an den Nutzer auf Deutsch:
- je Testpunkt: ok oder Fehler;
- Korrekturen mit Commits;
- offene Fragen.

Den Praxistest in `PR-3642.md`, `PR-3641.md` und `PR-3639.md` unter „Testing“ eintragen. Committen, `git fetch`, auf farm pushen.

**PRs stellt erst der Nutzer:**
- **#3642** sofort nach seiner Freigabe. Das Issue ist zugewiesen, und der Branch hängt von keinem offenen PR ab.
- **#3641** ebenfalls nach seiner Freigabe.
- **#3639** erst nach der Zuweisung.
- **#2933:** Zuerst muss im Issue mit dashu33 geklärt werden, wer was übernimmt. Bis dahin gibt es keinen Code.
