# Übergabe an die lokale Claude-Code-Sitzung: #3623 und #3248 testen, AI-Kennzeichnung bereinigen

Du arbeitest auf dem Windows-PC des Nutzers und erreichst den Druckserver per SSH (HP EliteDesk, Ubuntu 24.04, LAN `192.168.1.115`, Tailnet `100.112.171.42`, Bambuddy unter `/opt/bambuddy`). Sprich Deutsch mit dem Nutzer. Code, Commits und Texte für GitHub sind englisch.

Verbindlich ist `CLAUDE.md` auf `farm` von `balin77/bambuddy`, Abschnitte 1, 1a, 2, 4 und 5. **Besonders die neue Regel: keine AI-Kennzeichnung in allem, was an Upstream geht** (Commit `0628972bd`).

**Nichts an `maziggy/*` posten** ohne die ausdrückliche Freigabe des Nutzers: kein PR, kein Issue, kein Kommentar.

## Stand

- **#3623 Sprachauswahl für jeden Benutzer.** Issue offen, nicht zugewiesen.
  - Branch `feature/language-per-browser`.
  - Auf `farm`: `951f1d107` und die Anpassung `5c48f8674`. farm hat das Kontomenü aus upstream #3602 nicht, deshalb zeigt farm das **Globus-Symbol in der Seitenleiste für alle**, mit und ohne Anmeldung.
  - Es ändert nur die Sprache des eigenen Browsers. „Default language“ unter Settings → General gilt nur für SpoolBuddy-Displays, **nicht** für Benachrichtigungen.
- **#3248 Feinere Druckerrechte.** Das Issue gehört Minebuddy, balin77 hat es mit einem Kommentar erweitert. Nicht zugewiesen, der Maintainer hat noch nicht geantwortet.
  - Branch `feature/printer-permissions`.
  - Auf `farm`: `21b52090b`, `ca123ea38` und die Anpassung `831501854` (ohne Panda Breath).
  - Acht neue Rechte stehen eingerückt unter „Control Printers (includes the indented options)“: Pause and resume, Stop print, Filament, Temperatures/fans/speed/light, Move axes, Drying, Calibration and maintenance, Connection and debug.
  - `printers:control` bleibt der Oberbegriff. Bestehende Gruppen behalten alles, es gibt keine Migration.
  - Webhook Stop und Cancel brauchen jetzt `printers:stop`.
- **farm:** HEAD `371a261b2` bzw. neuer. CI ist grün, das Image `ghcr.io/balin77/bambuddy:farm` ist gebaut.
- **Entwürfe** in `farm/drafts/`: `PR-3623.md`, `WIKI-3623.md`, `PR-3248.md`, `WIKI-3248.md`. Screenshots auf `pr-assets` unter `3623/` und `3248/`.

## 1. AI-Kennzeichnung bereinigen (CLAUDE.md, Regel vom 19.11.)

Geprüft am 19.11. mit `git log upstream/dev..origin/<branch> --format='%an %ae %cn %ce%n%B' | grep -ciE "claude|anthropic"`:

| Branch | Treffer |
|---|---|
| `fix/button-text-selection` (#3577) | 18, muss bereinigt werden |
| `feature/printer-permissions` (#3248) | 9, muss bereinigt werden |
| `feature/language-per-browser`, `feature/spool-form-last-used`, `feature/queue-todo-list`, `feature/label-direct-print`, `feature/override-from-inventory`, `feature/queue-loaded-filament-first` | 0, schon sauber |

Für die zwei Branches:
1. Autor und Committer jedes Commits auf `Raphael <gublerra@gmail.com>` setzen. Die Zeilen `Co-Authored-By: Claude …` und `Claude-Session: …` aus den Nachrichten entfernen. Der Inhalt bleibt unverändert.
   Zum Beispiel mit
   `git rebase -i upstream/dev --exec 'git commit --amend --no-edit --reset-author'`
   plus `git filter-branch --msg-filter` oder `git rebase -x` mit `sed`, je nachdem, was einfacher ist.
2. Danach muss
   `git log upstream/dev..HEAD --format='%an %ae %cn %ce%n%B' | grep -i -E "claude|anthropic"`
   leer sein.
3. `git diff <alter-head> HEAD` muss leer sein, der Code darf sich also nicht ändern.
4. Mit `git push --force-with-lease=<branch>:<alter-head>` pushen. Es sind eigene Branches des Nutzers. Ist zu einem Branch schon ein PR offen, vorher den Nutzer fragen.
5. Die CI per `workflow_dispatch` (`ci.yml`) neu starten.

**PR- und Wiki-Entwürfe** in `farm/drafts/`: Aus diesen Dateien die Zeile „🤖 Generated with [Claude Code](https://claude.com/claude-code)“ und den Link `https://claude.ai/code/session_…` entfernen:
`PR-3248.md`, `PR-3575-plate-changer-capacity.md`, `PR-3576-clears-plate-per-job.md`, `PR-3577-button-text-selection.md`, `PR-3587.md`, `PR-3590.md`, `PR-3612.md`, `PR-3615.md`, `PR-3619.md`, `PR-3623.md`.
Auch die WIKI-Entwürfe und `ISSUE-*.md` mit `grep -n "Claude\|claude.ai"` prüfen. Das Ergebnis auf `farm` committen, als `Raphael`, ohne AI-Zeilen.

Neue Commits auf `farm` ebenfalls ohne AI-Zeilen, damit ein Cherry-Pick nichts mitbringt.

## 2. Server aktualisieren

1. Per SSH nach `/opt/bambuddy`.
2. `farm/update-bambuddy.sh` ausführen.
   - Nicht den Update-Knopf in der App benutzen.
   - **Niemals `docker compose down -v`.**
3. In der Oberfläche prüfen, dass `371a261b2` oder neuer läuft.

## 3. Test #3623: Sprache

1. **Als Mitarbeiter** (eingeschränkter Benutzer ohne Settings-Rechte, am besten in einem privaten Fenster bzw. auf seinem Handy): Unten in der Seitenleiste das **Globus-Symbol** antippen. Auf dem Handy liegt es im Menü ☰.
   - Eine Sprache wählen, zum Beispiel Deutsch. Die Oberfläche wechselt sofort.
   - Seite neu laden: Die Sprache bleibt.
2. **Als Admin auf einem anderen Gerät:** Die Sprache dort darf sich dadurch nicht ändern. Unter Settings → General zeigt **Default language** weiter den gespeicherten Wert.
3. Default language ändern: Die SpoolBuddy-Anzeige folgt. Die Browser-Sprache des Mitarbeiters bleibt seine eigene.
4. **Bekannte Grenze, kein Fehler:** Öffnet jemand SpoolBuddy in einem normalen Browser, setzt SpoolBuddy dort die Sprache auf den Default zurück. Das war schon vorher so.

## 4. Test #3248: Rechte für Mitarbeiter A

1. Settings → Authentifizierung → Gruppen → neue Gruppe „Mitarbeiter“:
   - **Printers:** Read an. Control Printers **aus**. Darunter **Pause and resume** und **Filament (load, unload, slot configure)** an. Optional Clear Plate.
   - **Inventory:** Read, Create, Update an; optional View Assignments. **Filaments:** Read. **K-Profiles:** Read. **Camera:** View, wenn gewünscht.
   - **Queue:** nur „Read All Queue“, wenn er die To-do-Liste (#3615) sehen soll.
   - Alles andere aus: Settings, Library, Archives, Projects, Users, Groups, Notifications und so weiter.
2. Den Benutzer der Gruppe zuordnen und bei Bedarf unter **Druckerzugriff** die Drucker einschränken.
3. Mit seinem Konto prüfen:
   - Während eines Drucks gehen **Pause und Fortsetzen**. **Stop**, Temperaturen, Lüfter, Licht, Achsen und Trocknen sind ausgegraut.
   - Spule im Inventar anlegen und einem Slot zuweisen. „Configure“ am Slot geht.
   - Settings, Modelle und Archiv erscheinen nicht im Menü.
   - Versucht er eine gesperrte Aktion trotzdem, lehnt der Server sie ab.
4. **Gegenprobe:** Eine bestehende Gruppe mit **Control Printers** (z. B. Operators) kann weiterhin alles.
5. **Gruppen-Editor:** Ist Control Printers angehakt, erscheinen die acht Unterrechte angehakt und ausgegraut, mit Hinweis „Included in Control Printers“.

## 5. Wenn etwas nicht stimmt

- Logs: `docker compose logs --since 10m bambuddy`
- Korrekturen:
  1. Auf dem Feature-Branch arbeiten (`feature/language-per-browser` bzw. `feature/printer-permissions`), als `Raphael`, ohne AI-Zeilen, mit Tests.
  2. Branch pushen und die CI per `workflow_dispatch` starten.
  3. Per `git cherry-pick -x` auf `farm` übernehmen. Changelog-Commits nicht.
  4. Vor jedem Push auf `farm` `git fetch` ausführen und die eigenen Commits obendrauf setzen. Auch Cloud-Sitzungen pushen dorthin.
- **Bekannte Grenzen:**
  - Die Rechte-Bezeichnungen im Gruppen-Editor sind nur englisch, wie die bestehenden Rechte.
  - Webhook-Start und Befehle über einen virtuellen Drucker brauchen weiter Control Printers.
  - Die Sprachauswahl gibt es nicht auf der Login-Seite.
- **Unbeständiger Test:** `EmbeddedCameraContext.test.tsx` („goes by the list fetched now…“) scheitert in der CI gelegentlich. Er hat mit diesen Features nichts zu tun, ein erneuter Lauf ist dann grün.

## 6. Ergebnis

Bericht an den Nutzer auf Deutsch:
- je Testpunkt: ok oder Fehler;
- Ergebnis der Bereinigung: Branches, neue HEADs, Prüfbefehl leer;
- gemachte Korrekturen mit Commits;
- offene Fragen.

Den Praxistest in `farm/drafts/PR-3623.md` und `PR-3248.md` unter „Testing“ abhaken. Committen, `git fetch`, auf `farm` pushen.

PRs stellt erst der Nutzer:
- **#3623** nach der Zuweisung.
- **#3248** erst, wenn der Maintainer der erweiterten Aufteilung zustimmt oder das Issue zuweist.
