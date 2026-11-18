# CLAUDE.md – Farm-Fork von Bambuddy (`balin77/bambuddy`)

Dieser Fork ergänzt [Bambuddy](https://github.com/maziggy/bambuddy) um
Funktionen für eine Bambu-Lab-Druckfarm mit **automatischem Plattenwechsel**
(AutoEject: SwapMod, JoBox, Push-off). Die Änderungen werden als Pull Request
an Upstream angeboten. Bis sie dort gemergt sind, läuft auf dem Druckserver
der Farm ein **eigenes Image aus diesem Fork**.

Sprich mit dem Nutzer **Deutsch**. Code, Commits, Issues und PRs an Upstream
sind **Englisch**.

Begleit-Repo mit Farm-Kontext: [balin77/autoeject-farm](https://github.com/balin77/autoeject-farm)
(`README.md`, `docs/ARCHITECTURE.md`, `docs/BAMBUDDY_SETUP.md`, `docs/PRINTERS.md`).

---

## 1. Branch-Modell

| Branch | Inhalt | Regeln |
|--------|--------|--------|
| `main`, `dev` | Spiegel von `maziggy/bambuddy` | **Nie** selbst committen. Nur per Sync auf Upstream-Stand bringen. |
| `feature/<name>` | Ein Feature für einen Upstream-PR | Abzweig von `upstream/dev`. Enthält **nur** den Feature-Code. **Keine** Farm-Dateien (diese `CLAUDE.md`, `farm/`, Farm-Workflow). |
| `farm` | Was auf dem Druckserver läuft: letztes Upstream-Release (`upstream/main`) + gemergte Feature-Branches + Farm-Dateien | Default-Branch des Forks. Daraus wird das Server-Image gebaut. |

Remotes einrichten:
```bash
git remote add upstream https://github.com/maziggy/bambuddy.git
git fetch upstream --tags
```

**Feature nach `farm` bringen: Cherry-Pick, kein Merge.** Feature-Branches
zweigen von `upstream/dev` ab. `dev` ist dem Release (`main`) meist um
viele Commits voraus. Ein `git merge feature/x` nach `farm` würde diesen
ganzen unveröffentlichten `dev`-Stand mitziehen. Deshalb:
```bash
git checkout farm
git cherry-pick -x <feature-commits>   # nur die eigenen Commits, ohne CHANGELOG
```
Konflikte entstehen typischerweise, weil `dev` an derselben Stelle schon
andere Zeilen eingefügt hat (i18n-Keys, Migrationen in `database.py`,
Formularfelder). Lösung: Aus jedem Konfliktblock **nur die Zeilen des
Features** übernehmen und die nur auf `dev` vorhandenen verwerfen. Danach
per `git grep` prüfen, dass keine dev-only-Bezeichner hereingerutscht sind,
und die betroffenen Tests, `tsc` und `check:i18n` laufen lassen.

**Sync bei neuem Upstream-Release** (z. B. wöchentlich oder bei neuem Tag):
1. `main`/`dev` des Forks auf `upstream/main`/`upstream/dev` vorspulen.
2. Feature-Branches auf `upstream/dev` rebasen und Tests laufen lassen.
3. `farm` neu aufbauen: `git merge upstream/main`. Für Features, die
   **noch nicht** im neuen Release sind, die Commits erneut per Cherry-Pick
   holen, falls der Merge sie verliert oder Konflikte macht. Tests laufen
   lassen und pushen. Daraus baut CI das neue Image.
4. Ist ein Feature im Upstream-Release enthalten, nichts mehr nach `farm`
   holen. Der Code kommt dann über `upstream/main`.

**Bekannte Testumgebung Windows:** Unter Windows schlagen einige
Upstream-Tests auch auf dem unveränderten Release fehl, z. B.
`test_force_color_plate_scope_migration.py` und
`test_send_all_timelapse_per_plate_3275.py`. Vor einer Fehlersuche immer
gegen ein sauberes `upstream/main` vergleichen (`git worktree add`).
Massgeblich ist Linux bzw. die CI.

## 1a. Stand (18.11.2026)

| Thema | Upstream | Im Fork |
|-------|----------|---------|
| Plattenbestätigung **pro Drucker** | Issue #2860 **geschlossen**: maziggy hat es selbst in `dev` gebaut (`6009a4a37`, Spalte `printers.require_plate_clear` BOOLEAN NULL, Modul `services/plate_clear.py`). PR #3540 (Draft, Keybored02) ist damit überholt. | Auf `farm` läuft **noch** der Entwurf von Keybored02 (`595d81fbc`, Spalte `plate_clear_override`). **Offen:** `farm` auf maziggys Version umstellen; dabei die Werte einmalig kopieren (`on` → TRUE, `off` → FALSE), sonst gehen die Einstellungen pro Drucker verloren. |
| Plattenzähler / Kapazität pro Drucker | Issue **#3575** (von uns, **balin77 zugewiesen**), Draft-PR #3588, Wiki-PR #148 | Feature B: `feature/plate-changer-capacity` (seit 18.11. auf `dev` mit #2860 umgestellt, ohne den Entwurf #3540; `farm` hat noch den alten Stand), auf `farm` (`c764a159`, `6b84c76a`). PR-/Wiki-Entwurf in `farm/drafts/` |
| Auto-Räumung **pro Datei/Auftrag** | Issue **#3576** (von uns, **balin77 zugewiesen**), Draft-PR #3589, Wiki-PR #149 | Feature A: `feature/clears-plate-per-job` (seit 18.11. auf `dev` mit #2860 umgestellt, neuer Lesezugriff `plate_clear.override()`; die UI-Texte nennen noch „Always require“; `farm` hat noch den alten Stand), auf `farm` (`ed0196ab`, `60aa5b43`) + Integration A+B (`57cf7da6`, `7d67ad29`, nur `farm`). Entwürfe in `farm/drafts/` |
| Button-Texte auf Touch markierbar, AMS-Slot-Kacheln per Tipp | Issue **#3577** (von uns, wartet auf Zuweisung; am 18.11. kommentiert, dass es fertig ist) | Feature C: `fix/button-text-selection` (auf `upstream/dev` rebased), auf `farm` (`e1782a8b`, `41eeb035`, Kacheln `89b56c76`, `ddd0c857`). Entwurf `farm/drafts/PR-3577-button-text-selection.md`, Screenshots `pr-assets/3577/` |
| Geladenes Filament zuerst (Queue-Modus mit Höchstwartezeit) | Issue **#3587** (von uns, wartet auf Zuweisung; am 18.11. kommentiert, dass es fertig ist) | `feature/queue-loaded-filament-first` (von `upstream/dev`), auf `farm` (`851b46ab`; dort ohne `model_dispatch_order`/#3536, Reservierung beachtet Plattengates und leere Plattenwechsler). Entwürfe `farm/drafts/PR-3587.md`, `WIKI-3587.md` |
| Filament-Override aus dem Lager mit Bestandshinweis | Issue **#3590** (von uns, balin77 zugewiesen); **PR #3618** gestellt am 18.11., Wiki-PR bambuddy-wiki#155 | `feature/override-from-inventory` (von `upstream/dev`), auf `farm` (`91c8cf45`, Anpassung `45f690a7`: ohne Support-Suffix #3559; Einstellung `5731dd90`). Auf Wunsch des Maintainers schaltet die installationsweite Einstellung `filament_override_inventory` (Standard **aus**, Checkbox „Show inventory colours“ im Druckdialog und Karte unter Queue & Dispatch) alles von #3590. **Auf der Farm nach dem Update einmal einschalten.** Neues Ereignis „Filament Out of Stock“ (aus per Default). Entwürfe `farm/drafts/PR-3590.md`, `WIKI-3590.md`, Screenshots `pr-assets/3590/` |
| Etiketten direkt auf Brother-QL-Netzwerkdrucker | Issue **#3612** (von uns, wartet auf Zuweisung; am 18.11. kommentiert, dass es fertig und getestet ist) | `feature/label-direct-print` (von `upstream/dev`), auf `farm` (`61f18fff`). Eigene Umsetzung des Brother-Rasterprotokolls über TCP 9100, keine neue Abhängigkeit; Druck als Job (202 + Abfrage). Einstellung unter Settings → Filament → Label printer (ohne Eintrag ändert sich nichts). Entwürfe `farm/drafts/PR-3612.md`, `WIKI-3612.md`, Screenshots `pr-assets/3612/`. Am QL-820NWB getestet (Testdruck, 40 mm, 20 mm; kurze Etiketten quer, Farbname vor HEX-Code). |
| „To do“-Liste für die Warteschlange | Issue **#3615** (von uns, nicht zugewiesen) | Noch kein Code; Auftrag für eine Cloud-Sitzung |
| QR-Foto liest kleine Etiketten nicht | Issue **#3616** (von uns, nicht zugewiesen) | Noch kein Code; Auftrag für eine Cloud-Sitzung |
| Spule anlegen: letzte Werte, Farben und Leerspulen der Marke | Issue **#3619** (von uns, nicht zugewiesen) | Noch kein Code; Auftrag für eine Cloud-Sitzung |

Wer von A und B **zweiter** upstream landet, übernimmt die Integration aus
`57cf7da6`: `consume_auto_cleared_plate(..., job_clears_plate=...)`.

Upstream-PRs werden erst gestellt, wenn das Issue dem Nutzer (`balin77`)
zugewiesen ist. Bis dahin entsteht der Code auf `feature/*` und läuft über
`farm` auf dem Server.

## 2. Harte Regeln

### Upstream-Regeln (aus `CONTRIBUTING.md`, verbindlich)
- **Erst ein Issue, dann ein PR.** Ohne zugewiesenes Issue schliesst Upstream
  den PR. Den Issue-Text entwirfst du, der **Nutzer** prüft ihn und gibt frei.
  Erst danach wird er gepostet.
- PRs gehen **gegen `dev`**, nie gegen `main`. Pro PR genau ein Feature, das
  PR-Template vollständig ausfüllen, Screenshots für UI-Änderungen beilegen.
- Für neue Features ist ein **Begleit-PR in `maziggy/bambuddy-wiki`** Pflicht.
  Im Code-PR verlinken.
- **i18n:** Keine hartkodierten UI-Texte. Neue Keys in **jede** Locale-Datei in
  `frontend/src/i18n/locales/`, mit **echten** Übersetzungen.
  `npm run check:i18n` muss grün sein.
- **Auth:** Neue Endpunkte über `RequirePermissionIfAuthEnabled` absichern.
  Neue Permissions im Enum, in `PERMISSION_CATEGORIES` und in den Standardgruppen eintragen.
- **DB:** Jede neue Spalte braucht eine Migration in
  `backend/app/core/database.py`, die exakt dem Model entspricht
  (Nullability, Default). Migrationen nur **additiv**, mit Defaults, die das
  bisherige Verhalten beibehalten. `scripts/check_postgres_upgrade.py` muss
  bestehen.
- **Qualität:** Ruff (lint + format), basedpyright gegen die Baseline, ESLint,
  `tsc`, knip und Vitest müssen grün sein, ebenso pytest (unit + integration).
  Neue Logik bekommt Tests. Lokal: `./test_backend.sh`, `./test_frontend.sh`.

### Eigene Regeln
- **Nach aussen nur mit Freigabe:** Issues, PRs, Kommentare an `maziggy/*`
  sowie das Löschen von Branches oder Tags im Fork **erst nach ausdrücklicher
  Freigabe durch den Nutzer**. Pushen auf eigene Feature-Branches und auf
  `farm` im Fork ist erlaubt.
- **Kein AutoEject-Code in Bambuddy.** Die Features bleiben generisch, z. B.
  „Drucker räumt die Platte selbst“. G-Code-Bausteine, Merge-Logik und
  Wechselsystem-Spezifika bleiben im Repo `autoeject`. Damit fällt AutoEject
  nicht unter die AGPL.
- **AGPL:** Der Quellcode der auf dem Server laufenden Version liegt immer
  öffentlich auf `farm` in diesem Fork. Den Fork nicht privat schalten.
- Keine Secrets ins Repo (Access Codes, API-Keys, Tailscale-Daten).
- **DRY:** Erst nach bestehenden Funktionen suchen und diese erweitern, statt
  daneben neue zu schreiben. Muster und Stil von Bambuddy übernehmen. Wenn
  ein Feature in die Codebasis passt wie von Upstream geschrieben, hat der PR
  die besten Chancen.

## 3. Features

Alle Features bauen auf der Override-Einstellung pro Drucker aus #3540 auf
(`printers.plate_clear_override`, `_plate_gate()` im Scheduler). Diese
Einstellung erweitern, keine parallele Logik bauen.

### Feature A – Automatische Plattenräumung pro Datei, Issue #3576 (`feature/clears-plate-per-job`)

Vorrang: Steht ein Drucker auf *Immer verlangen*, wartet er immer. Das Flag
wirkt nur dort, wo sonst die globale Einstellung greifen würde.

**Problem:** Die globale Einstellung `require_plate_clear` lässt die
Warteschlange nach jedem fertigen Druck auf die Bestätigung „Platte geräumt“
warten. Drucker mit automatischem Plattenwechsel (die Datei enthält die
Wechsel- bzw. Push-off-Sequenz am Ende) müssten sofort weiterdrucken. Drucker
ohne Wechsler dürfen das **nicht**. Ein globaler Schalter passt also nie für
die ganze Farm.

**Soll:**
- Eine Datei in der Library lässt sich als **„räumt die Platte automatisch“**
  kennzeichnen, z. B. als Option beim Upload oder im Datei-Detail/Bearbeiten.
- Im Druck-/Queue-Dialog gibt es pro Auftrag denselben Schalter, vorbelegt
  aus der Datei und überschreibbar. Er gilt auch für Reprints aus dem Archiv.
- Beendet ein Drucker einen Queue-Auftrag **erfolgreich** und hat der Auftrag
  das Flag gesetzt, wartet der Scheduler **nicht** auf die Plattenbestätigung
  und startet den nächsten passenden Auftrag. Dabei die vorhandene
  Plate-Clear-Logik und `awaiting_plate_clear` erweitern, keine zweite daneben
  bauen.
- Bei **fehlgeschlagenem oder abgebrochenem** Druck bleibt alles wie bisher:
  Plattenbestätigung nötig, `require_previous_success` greift.
- Ist `require_plate_clear` global aus, ändert sich nichts.
- Ohne gesetztes Flag verhält sich alles exakt wie bisher (Default `false`).
- Tests: Scheduler-Unit-Tests für Erfolg, Fehler und Abbruch, mit und ohne
  Flag, mit und ohne globalen Schalter. Dazu API-Tests, Migrationstest und
  Frontend-Tests für Dialog und Schalter.

### Feature B – Kapazität des Plattenwechslers pro Drucker, Issue #3575 (`feature/plate-changer-capacity`)

Zählt bei jedem erfolgreich beendeten Auftrag herunter, dessen Platte
automatisch geräumt wurde: entweder weil der Drucker auf *Nie verlangen*
steht (#3540) oder weil der Auftrag das Flag aus Feature A hat.
Datenfelder laut Issue: `printers.plate_capacity`, `printers.plates_remaining`.

**Problem:** Bambuddy weiss nicht, wie viele Platten im Wechsler liegen bzw.
wie viel Platz im Auffangbehälter ist. Startet ein automatisch räumender
Druck bei leerem Magazin oder vollem Behälter, kann das den Drucker
beschädigen. Das ist **die wichtigste Sicherheitsregel der Farm**.

**Soll (Plan von Agenten verfeinern lassen):**
- Pro Drucker optional eine **Kapazität** (z. B. 5) und ein Zähler
  „verbleibend“.
- Jeder erfolgreich beendete Auftrag mit Auto-Räumung zählt 1 herunter.
- Bei 0 bekommt der Drucker **keine** weiteren Auto-Räumungs-Aufträge mehr
  und wartet. Es gibt eine Benachrichtigung über die bestehenden
  Notification-Provider.
- Auf der Druckerkarte steht die Anzeige „x / y“ mit einem Button
  „Nachgefüllt / Geleert“, der den Zähler zurücksetzt.
- Ohne gesetzte Kapazität ändert sich nichts.

### Feature C – Button-Texte nicht markierbar, Issue #3577 (`fix/button-text-selection`)

Eine globale CSS-Regel in `frontend/src/index.css` für `button` und
`[role='button']`: `user-select: none`, `-webkit-user-select: none`,
`-webkit-touch-callout: none`. Eingabefelder und normaler Text bleiben
markierbar. Erweitert: die AMS-Slot-Kacheln in `FilamentHoverCard.tsx` sind
Buttons (Tipp, Enter, Leertaste öffnen die Karte; zweiter Tipp, Tipp daneben,
Escape oder Fokus weg schliessen; immer nur eine Karte offen; Maus-Hover
unverändert). Kein Wiki-PR nötig (keine neue Einstellung, kein neuer Ablauf).

**Reihenfolge:** C und B können parallel laufen, A danach. B ist für die
Sicherheit der Farm am wichtigsten. Auf `farm` kommen alle drei.

## 4. Deployment auf den Druckserver

**Server:** HP EliteDesk, Ubuntu 24.04, im LAN `192.168.1.115`, im Tailnet
`100.112.171.42`. Bambuddy liegt unter `/opt/bambuddy`, mit der **offiziellen,
unveränderten** `docker-compose.yml` und einer `.env`. Daten liegen in den
Docker-Volumes `bambuddy_bambuddy_data` und `bambuddy_bambuddy_logs`.
**Eine Cloud-Sitzung erreicht den Server nicht.** Die Schritte auf dem Server
erledigt eine lokale Claude-Code-Sitzung auf dem Windows-PC des Nutzers per
SSH, nachdem das Image existiert.

**Prinzip: Image wechseln, Daten behalten.**
- GitHub-Actions-Workflow `farm-image.yml`, **nur auf `farm`**: Bei jedem
  Push auf `farm` und per `workflow_dispatch` wird aus dem `Dockerfile` des
  Repos ein `linux/amd64`-Image gebaut und nach
  `ghcr.io/balin77/bambuddy:farm` sowie `:farm-<kurz-sha>` gepusht. Das Paket
  ist öffentlich, der Server braucht also kein Login. Die Version in der UI
  soll als Farm-Build erkennbar sein, z. B. mit Suffix `+farm.<sha>`, falls
  Bambuddy die Version aus Build-Args oder Umgebung liest.
- Upstream-Workflows im Fork: `ci.yml` und `codeql.yml` bleiben aktiv, sie
  testen die Feature-Branches. `cleanup-ghcr`, `stale`, `repo-stats`,
  `issue-closed`, `auto-label-area` und `windows-installer` im Fork mit
  `gh workflow disable` deaktivieren. Die Dateien selbst nicht löschen.
- Auf dem Server bleibt die Upstream-`docker-compose.yml` unangetastet.
  Daneben kommt eine `docker-compose.override.yml`, die nur
  `image: ghcr.io/balin77/bambuddy:farm` setzt. Der Compose-Projektname bleibt
  `bambuddy`, damit bleiben dieselben Volumes erhalten. **Niemals
  `docker compose down -v`.**
- Im Fork unter `farm/` liegen `farm/docker-compose.override.yml` und
  `farm/update-bambuddy.sh` als Vorlagen. Das Skript macht Folgendes:
  1. Backup: Die Volumes per Wegwerf-Container als `tar.gz` nach
     `/opt/bambuddy/backups/` sichern. Vorher den Container kurz stoppen,
     damit die SQLite-DB konsistent ist. Die letzten 10 Backups behalten.
  2. Den Image-Digest vor dem Update merken.
  3. `docker compose pull && docker compose up -d`.
  4. Healthcheck bis zu 3 Minuten abwarten: Container `healthy` und
     HTTP 200 auf `:8000`.
  5. Scheitert der Healthcheck: Rollback auf den gemerkten Digest, bei
     Bedarf DB-Backup zurückspielen. Die Schritte loggen.
- Den In-App-Update-Button von Bambuddy nicht verwenden, er zeigt auf
  Upstream. Updates laufen nur über das Skript.
- Rückweg zu reinem Upstream: Die Override-Datei entfernen und `up -d`
  ausführen. Additive Migrationen hinterlassen höchstens ungenutzte Spalten.

## 5. Arbeitsweise mit Agenten

Der Nutzer wünscht **ausdrücklich Multi-Agenten-Orchestrierung** mit
paralleler Arbeit, wo immer sie möglich ist.

**Master (Opus)** leitet alles. Er plant, verteilt die Arbeit, führt die
Ergebnisse zusammen, entscheidet über die Review-Funde und berichtet dem
Nutzer. Er programmiert nicht selbst in der Breite.

Modellwahl:
| Aufgabe | Modell |
|---------|--------|
| Codebasis erkunden (Scheduler, Plate-Clear, Queue, Library, Migrationen, Frontend-Dialog) | `sonnet` (Explore), mehrere parallel |
| Gesamtplan / Architekturentscheidungen | `opus` (Plan) |
| Umsetzung | `sonnet`, **parallel** nach Schichten mit klaren Dateigrenzen: (1) Model, Migration, Schemas, API; (2) Scheduler-Logik; (3) Frontend-Dialog, Library-UI, Druckerkarte; (4) i18n aller Locales; (5) Tests. Verträge (Feldnamen, API-Shape) legt der Plan vorher fest. |
| Mechanisches: Lint-/Format-Fixes, Testläufe auswerten | `haiku` oder `sonnet` |
| Reviews | `opus`, **parallel nach Dimension**: Scheduler-Korrektheit und Nebenläufigkeit (Race zwischen FINISH und Dispatch, Doppelstart, Fehlerfälle); DB/Migration/PostgreSQL; Auth/Permissions/Security; Frontend/i18n/UX; Upstream-Tauglichkeit (Stil, Umfang, CONTRIBUTING) |
| Verifikation einzelner Review-Funde | `sonnet`, je Fund ein Agent, prüft gegen den Code und verwirft Fehlalarme |

**Zyklus:** Umsetzen, dann parallele Reviews, dann Funde verifizieren, dann
fixen (parallel nach Datei), dann erneut reviewen. Das wiederholt sich, bis
**keine schwerwiegenden Funde** mehr übrig sind (Korrektheit,
Datenverlust/Sicherheit, rote Tests/CI, Verstoss gegen Upstream-Regeln).
Spätestens nach 4 Runden mit dem Nutzer Rücksprache halten.
Kleine Nebenbefunde direkt fixen, wenn sie eindeutig und risikolos sind.
Sonst dem Nutzer vorlegen und die Aufgabe nicht ungefragt aufblähen.

**Definition of Done pro Feature:**
- Alle lokalen Test-Skripte und die CI auf dem Feature-Branch sind grün.
- Die letzte Review-Runde hat keine schwerwiegenden Funde mehr ergeben.
- Der Branch ist in `farm` gemergt, das Image ist gebaut und unter
  `ghcr.io/balin77/bambuddy:farm` verfügbar.
- Die Entwürfe für Issue-Text, PR-Beschreibung (Englisch) und Wiki-Änderung
  liegen dem Nutzer zur Freigabe vor.
- Der Nutzer bekommt eine kurze deutsche Zusammenfassung: was geändert
  wurde, wie man es in der UI benutzt und was auf dem Server zu tun ist.
