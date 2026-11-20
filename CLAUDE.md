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

## 1a. Stand (19.11.2026)

| Thema | Upstream | Im Fork |
|-------|----------|---------|
| Plattenbestätigung **pro Drucker** | Issue #2860 **geschlossen**: maziggy hat es selbst in `dev` gebaut (`6009a4a37`, Spalte `printers.require_plate_clear` BOOLEAN NULL, Modul `services/plate_clear.py`). PR #3540 (Draft, Keybored02) ist damit überholt. | Auf `farm` seit 18.11. maziggys Version (`9099c8c2a`, Cherry-Pick von `6009a4a37`); der Entwurf von Keybored02 (`595d81fbc`) ist zurückgenommen (`f5150aa25`). Die alte Spalte `printers.plate_clear_override` bleibt in bestehenden Datenbanken liegen (Rollback); eine Farm-Migration kopiert ihre Werte **einmalig** nach `require_plate_clear` (`on` → TRUE, `off` → FALSE, sonst NULL; Marker `_migrate_farm_plate_clear_override_done` in `settings`, `22ddb2f5d`). Diese Migration bleibt auf `farm`, bis kein Server mehr die alte Spalte hat. |
| Plattenzähler / Kapazität pro Drucker | Issue **#3575** (von uns, **balin77 zugewiesen**), PR #3588 (ready seit 18.11.), Wiki-PR #148 | Feature B: `feature/plate-changer-capacity` (seit 18.11. auf `dev` mit #2860 umgestellt, ohne den Entwurf #3540), auf `farm` (`c764a159`, `6b84c76a`, Umstellung auf #2860 `d3e6c3c3b`). PR-/Wiki-Entwurf in `farm/drafts/` |
| Auto-Räumung **pro Datei/Auftrag** | Issue **#3576** (von uns, **balin77 zugewiesen**), PR #3589 (ready seit 19.11.), Wiki-PR #149 | Feature A: `feature/clears-plate-per-job` (seit 18.11. auf `dev` mit #2860 umgestellt, neuer Lesezugriff `plate_clear.override()`), auf `farm` (`ed0196ab`, `60aa5b43`, Umstellung auf #2860 `d3e6c3c3b`, UI-Texte `ccbbf0e17`) + Integration A+B (`57cf7da6`, `7d67ad29`, `d3e6c3c3b`, nur `farm`). Entwürfe in `farm/drafts/` |
| Button-Texte auf Touch markierbar, AMS-Slot-Kacheln per Tipp | Issue **#3577** **geschlossen**: maziggy hat es am 19.11. selbst in `dev` behoben (`d38e6fad9`). Kein PR. Unsere Version auf `farm` entfällt mit dem nächsten Release. | Feature C: `fix/button-text-selection` (auf `upstream/dev` rebased), auf `farm` (`e1782a8b`, `41eeb035`, Kacheln `89b56c76`, `ddd0c857`). Entwurf `farm/drafts/PR-3577-button-text-selection.md`, Screenshots `pr-assets/3577/` |
| Geladenes Filament zuerst (Queue-Modus mit Höchstwartezeit) | Issue **#3587** (von uns, seit 19.11. balin77 zugewiesen); **PR #3627** gestellt am 19.11., Wiki-PR bambuddy-wiki#159 | `feature/queue-loaded-filament-first` (von `upstream/dev`), auf `farm` (`851b46ab`; dort ohne `model_dispatch_order`/#3536, Reservierung beachtet Plattengates und leere Plattenwechsler). Entwürfe `farm/drafts/PR-3587.md`, `WIKI-3587.md` |
| Filament-Override aus dem Lager mit Bestandshinweis | Issue **#3590** (von uns, balin77 zugewiesen); **PR #3618** gestellt am 18.11., Wiki-PR bambuddy-wiki#155. Review von maziggy am 19.11. (Änderungen verlangt, 6 Punkte); Korrekturen als 8 neue Commits gepusht (`6c0ff0a39` bis `92bf5007a`), seit 19.11. per Cherry-Pick auf `farm`. Ebenso die Review-Korrekturen zu #3626 (#3619) und #3622 (#3615, 7 Commits bis `2586196b7`). | `feature/override-from-inventory` (von `upstream/dev`), auf `farm` (`91c8cf45`, Anpassung `45f690a7`: ohne Support-Suffix #3559; Einstellung `5731dd90`). Auf Wunsch des Maintainers schaltet die installationsweite Einstellung `filament_override_inventory` (Standard **aus**, Checkbox „Show inventory colours“ im Druckdialog und Karte unter Queue & Dispatch) alles von #3590. **Auf der Farm nach dem Update einmal einschalten.** Neues Ereignis „Filament Out of Stock“ (aus per Default). Entwürfe `farm/drafts/PR-3590.md`, `WIKI-3590.md`, Screenshots `pr-assets/3590/` |
| Etiketten direkt auf Brother-QL-Netzwerkdrucker | Issue **#3612** (von uns, seit 19.11. balin77 zugewiesen); **PR #3630** gestellt am 19.11., Wiki-PR bambuddy-wiki#160. Branch auf `dev` mit #3621 (Zeilenumbruch) zusammengeführt; `farm` hat noch den Stand davor. | `feature/label-direct-print` (von `upstream/dev`), auf `farm` (`61f18fff`). Eigene Umsetzung des Brother-Rasterprotokolls über TCP 9100, keine neue Abhängigkeit; Druck als Job (202 + Abfrage). Einstellung unter Settings → Filament → Label printer (ohne Eintrag ändert sich nichts). Entwürfe `farm/drafts/PR-3612.md`, `WIKI-3612.md`, Screenshots `pr-assets/3612/`. Am QL-820NWB getestet (Testdruck, 40 mm, 20 mm; kurze Etiketten quer, Farbname vor HEX-Code). |
| „To do“-Liste für die Warteschlange | Issue **#3615** (von uns, seit 19.11. balin77 zugewiesen); **PR #3622** gestellt am 19.11., Wiki-PR bambuddy-wiki#156. Farm-Test an echten Druckern steht noch aus und ist im PR so vermerkt. | `feature/queue-todo-list` (von `upstream/dev`), auf `farm` (Cherry-Pick `267ac48a5`, Anpassung `6685e67e4`; farm-Erweiterung `41fa73323`, `0ada8e79f`: Plattenwechsler leer #3575, Priorität #3587, Lagerhinweis #3590). Strukturierte Aufzeichnung neben dem Wartetext, kein Parsen, keine Migration. Entwürfe `farm/drafts/PR-3615.md`, `WIKI-3615.md`, Screenshots `pr-assets/3615/` |
| QR-Foto liest kleine Etiketten nicht | Issue **#3616** **geschlossen**: maziggy hat es am 19.11. selbst in `dev` behoben. | Kein eigener Code nötig. |
| Spule anlegen: letzte Werte, Farben und Leerspulen der Marke | Issue **#3619** (von uns, seit 19.11. balin77 zugewiesen); **PR #3626** gestellt am 19.11., Wiki-PR bambuddy-wiki#158 | `feature/spool-form-last-used` (von `upstream/dev`), auf `farm` (`07ba7c5a1` letzte Werte, `0bd00a956` Tests, `c088452f8` Fix `+`-Zweig, `dc6d5f0e2` Produktlinien + Show all colours, `c84cf0a43` Leerspulen der Marke). Nur Frontend, localStorage, keine Migration. Spoolman-Filament-Verknüpfung wird nicht gemerkt (Farbe gehört dazu). Entwürfe `farm/drafts/PR-3619.md`, `WIKI-3619.md`, Screenshots `pr-assets/3619/` |
| Sprachauswahl für jeden Benutzer | Issue **#3623** (von uns, seit 19.11. balin77 zugewiesen); **PR #3625** gestellt am 19.11., Wiki-PR bambuddy-wiki#157 | `feature/language-per-browser` (von `upstream/dev`, Kontomenü #3602), auf `farm` (`951f1d107`, Anpassung `5c48f8674`: farm hat kein Kontomenü, daher Globus-Symbol in der Seitenleiste für alle). Ändert nur die Sprache des Browsers; „Default language“ in Settings gilt für SpoolBuddy. Entwürfe `farm/drafts/PR-3623.md`, `WIKI-3623.md`, Screenshots `pr-assets/3623/` |
| Feinere Druckerrechte unter Control Printers | Issue **#3248** (von Minebuddy; unser Kommentar erweitert es, nicht zugewiesen, keine Antwort des Maintainers) | `feature/printer-permissions` (von `upstream/dev`); auf `farm` (`21b52090b`, `ca123ea38`, Anpassung `831501854`: ohne Panda Breath). Webhook Stop/Cancel brauchen `printers:stop`, Webhook-Start und Virtual-Printer-MQTT bleiben auf `printers:control`; Diagnose bleibt auf `printers:read`. Acht Rechte (pause_resume, stop, filament, tune, motion, drying, maintenance, admin), `printers:control` bleibt Oberbegriff, keine Migration. Entwürfe `farm/drafts/PR-3248.md`, `WIKI-3248.md`, Screenshots `pr-assets/3248/` |
| Gruppen-Option: nicht erlaubte Bedienelemente der Druckerseite ausblenden | Issue **#3639** (von uns, gestellt am 20.11., nicht zugewiesen) | Noch kein Code; Auftrag für eine Cloud-Sitzung. Upstream-Branch unabhängig von #3248, auf `farm` mit den feinen Rechten zusammenführen. Entwurf `farm/drafts/ISSUE-hide-unpermitted-controls.md` |
| To-do-Liste: Filamente der nächsten Aufträge vorbereiten („Prepare“) | Issue **#3640** (von uns, gestellt am 20.11., nicht zugewiesen); PR erst nach dem Merge von #3622 und #3634 | `feature/queue-todo-prepare` (auf `feature/queue-todo-replace-slot`), Commits tragen noch den Platzhalter `#PREPARE`; noch nicht auf `farm`. Entwurf `farm/drafts/ISSUE-todo-prepare.md` |
| Benachrichtigungen: lesbares Format, Code `filament_short`, Sprache | Issues **#3641** (Feature) und **#3642** (Fehler), beide von uns, gestellt am 20.11., nicht zugewiesen; Kommentar zu **#2933** (Sprache, fremdes Issue) | Noch kein Code; Auftrag für eine Cloud-Sitzung. Entwurf `farm/drafts/ISSUE-notification-format.md`, Screenshot `pr-assets/issues/filament-short-notification.png` |
| Drucker hinzufügen: Prüfung zurücksetzen, Zugangscode anzeigen | Issue **#3624** **geschlossen**: maziggy hat es am 19.11. selbst in `dev` behoben. | Kein eigener Code. |
| Versionen im Dateimanager als eine Karte | Issue **#3628** (von uns, gestellt am 19.11., zugewiesen an balin77, noch kein PR) | `feature/variant-group-card` (von `upstream/dev`), auf `farm` (`3496a8c71`..`59518e80c`, Anpassung `78623e671`: ConfirmModal `dismissible`, `clears_plate` der Alternativen bei Gruppendruck). **Backend berührt:** `GET /library/files?with_variant_members=true` (additiv) und Rechte der Variant-Group-Endpunkte (nur lesbare Mitglieder; Ändern nur, wer alle aktiven Mitglieder besitzt oder update_all hat). Häkchen auf der Karte wählt nur Versionen im aktuellen Ordner; Print druckt alle sichtbaren als einen Auftrag. Keine Migration. Entwürfe `farm/drafts/PR-3628.md`, `WIKI-3628.md`, Screenshots `pr-assets/3628/` Kachelansicht klappt als Popover auf (Desktop) bzw. Blatt von unten (Handy), Raster bleibt ruhig (`27566c5f5`, `75ba81e74`, `5d6b00531`). |
| Katalogfarben im Spulen-Formular nach Farbe oder Name | Issue **#3633** (von uns, gestellt am 19.11., nicht zugewiesen) | `feature/spool-form-color-order` (**von `feature/spool-form-last-used`**, also auf PR #3626; PR erst nach dessen Merge), auf `farm` (`71f42fc01`). Umschalter A–Z / Farbkreis, `colorSortKey` aus #2729 wiederverwendet, Clear über `sortHex` mit Alpha, bei Show all colors jeder Block für sich sortiert, localStorage `bambuddy-catalog-color-order`. Nur Frontend. Entwürfe `farm/drafts/PR-3633.md`, `WIKI-3633.md` (Wiki hängt an bambuddy-wiki#158), Screenshots `pr-assets/3633/` |
| To-do-Liste nennt den Slot für fehlendes Filament | Issue **#3634** (von uns, gestellt am 19.11., nicht zugewiesen) | `feature/queue-todo-replace-slot` (**von `feature/queue-todo-list`**, also auf PR #3622; PR erst nach dessen Merge), auf `farm` (`1b9a33226`, `356c6f4bd`, `e6d347ee4`, `541abc228`, `54f5a42ef`, Anpassung `874dbbe1f`). Hinweis entsteht in einem eigenen Schritt am Ende jedes Scheduler-Durchlaufs (nur Drucker mit Filament-Halt, Savepoint, Cache pro Drucker), API additiv `slot_hint`/`slot_hints` an `GET /queue/todo`. Scheduler-Entscheidungen unverändert. Entwürfe `farm/drafts/PR-3634.md`, `WIKI-3634.md` (Wiki hängt an bambuddy-wiki#156), Screenshots `pr-assets/3634/` |

**Offene PRs nicht mehr umschreiben:** maziggy merged `dev` selbst in unsere PR-Branches (gesehen bei #3618 und #3622). Sobald ein PR offen ist: kein Rebase, kein Force-Push, nur neue Commits obendrauf.

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
- **Keine AI-Kennzeichnung in allem, was an Upstream geht.** Der Maintainer
  hat am 19.11.2026 auf den PRs #3588 und #3589 verlangt: „I don't want to
  have AI commits in the repo. Please remove." Deshalb auf `feature/*`,
  `fix/*` und den Wiki-Branches (`balin77/bambuddy-wiki`):
  - **Autor und Committer** jedes Commits ist der Nutzer
    (`Raphael <gublerra@gmail.com>`), nie `Claude <noreply@anthropic.com>`.
    In einer Cloud-Sitzung vor dem ersten Commit setzen:
    `git config user.name "Raphael"` und
    `git config user.email "gublerra@gmail.com"`.
  - **Keine Zeilen** `Co-Authored-By: Claude …`, `Claude-Session: …` oder
    andere Hinweise auf ein AI-Werkzeug in Commit-Nachrichten. Das gilt auch
    dann, wenn die Werkzeug-Voreinstellung solche Zeilen anhängen will.
  - **PR-Beschreibungen, Issue-Texte und Kommentare** ohne „Generated with
    Claude Code" und ohne Links auf claude.ai-Sitzungen.
  - Vor jedem Push prüfen:
    `git log upstream/dev..HEAD --format='%an %ae %cn %ce%n%B' | grep -i -E "claude|anthropic"`
    muss leer sein.
  - Auf `farm` dürfen ältere Commits die Zeilen behalten (nur der Fork).
    Neue Commits auch dort ohne, damit ein Cherry-Pick nichts mitbringt.

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

Alle Features bauen auf der Einstellung pro Drucker aus #2860 auf
(`printers.require_plate_clear`: TRUE/FALSE, NULL folgt der App-Einstellung;
Modul `services/plate_clear.py` mit `applies()` und `override()`). Diese
Einstellung erweitern, keine parallele Logik bauen.

### Feature A – Automatische Plattenräumung pro Datei, Issue #3576 (`feature/clears-plate-per-job`)

Vorrang: Steht die Einstellung eines Druckers auf *An*, wartet er immer. Das Flag
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
automatisch geräumt wurde: entweder weil die Einstellung des Druckers auf
*Aus* steht (#2860) oder weil der Auftrag das Flag aus Feature A hat.
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
