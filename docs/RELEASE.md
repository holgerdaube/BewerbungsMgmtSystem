# Release — Versionen und Freigabe (intern, P2-51, P2-82, P2-84)

Wie du eine neue BMS-Version freigibst und als Paket in einem GitHub-Release veröffentlichst. Das
BMS ist Open Source (Apache-2.0): Es gibt seit P2-82 keine Lizenzdatei und keinen Paketdienst mehr.
Anwender finden neue Versionen im GitHub-Release des öffentlichen Repos
`holgerdaube/BewerbungsMgmtSystem`. Diese Doku ist für die Projektleitung, nicht für Anwender — sie wird
nicht mitgeliefert (`docs/RELEASE.md` fällt über die Doku-Positivliste in
`pipeline/kundenpaket.py::DOKU_ERLAUBT` aus jedem Paket heraus).

**Zwei Repositories.** Entwickelt wird in einem nicht öffentlichen Entwicklungs-Repository; das öffentliche
Repo entsteht aus einem Export des geprüften Stands (Abschnitt „Veröffentlichen“ unten). Eine Freigabe
(`freigeben`) legt Version, CHANGELOG, Commit und Tag im Entwicklungs-Repo an; ein Release entsteht dort
nicht: `release.yml` läuft bei einem Tag-Push nur im öffentlichen Repo (beide Jobs prüfen den Repo-Namen).
Der Probebau per `workflow_dispatch` läuft in jedem Repo. Update-Knopf und Update-Werkzeug fragen immer das
öffentliche Repo; steht dort noch kein Release, finden sie nichts („Es ist noch keine Version
veröffentlicht.“ bzw. ein Verbindungsfehler).

Kurzfassung, Details unten:

```sh
scripts/release.sh freigeben patch --probe        # nur pruefen
scripts/release.sh freigeben patch                # Entwicklungs-Repo: Version, CHANGELOG, Commit, Tag, Push
scripts/veroeffentlichen.sh --ziel <Arbeitskopie> --ref v1.1.0   # geprueften Stand in die Arbeitskopie des oeffentlichen Repos
# … committen, pushen, CI abwarten, taggen, Tag pushen (Abschnitt „Veröffentlichen“): das Tag startet das Release …
scripts/release.sh abholen 1.1.0                  # laedt ZIP + .sha256 aus dem Release (nur zum Pruefen)
# … Das GitHub-Release im öffentlichen Repo ist die Veroeffentlichung, danach folgt kein weiterer Schritt (Schritt 5 unten) …
```

`scripts/release.sh` und `scripts/veroeffentlichen.sh` reichen alle Argumente 1:1 an `python -m pipeline.release`
bzw. `python -m pipeline.veroeffentlichung` (aus `backend/`) durch — die Beispiele unten nutzen die Skripte.

## Versionsschema

SemVer, Quelle ist die Datei `VERSION` im Projekt-Root (eine Zeile `MAJOR.MINOR.PATCH`). `0.0.0`
heißt „noch keine Freigabe". Nur `pipeline/release.py::freigeben()` schreibt diese Datei — von
Hand nie anfassen. Jede Freigabe legt zusätzlich ein annotiertes Git-Tag `vX.Y.Z` an; Tag und
`VERSION` müssen immer übereinstimmen (`release.yml` prüft das bei jedem Tag-Push noch einmal
nach).

Faustregel für die Stufe:
- **patch** — Fehlerbehebung, keine sichtbare neue Funktion.
- **minor** — neue Funktion, nichts Bestehendes bricht.
- **major** — etwas, das ein Anwender als Bruch erleben könnte (2.0.0: Wegfall der Lizenzpflicht und
  neuer Update-Weg über GitHub, s. P2-82).

`scripts/release.sh freigeben <X.Y.Z|patch|minor|major>` nimmt beides an: eine feste Version oder
eine Stufe, die gegen die aktuelle `VERSION` hochgezählt wird.

## CHANGELOG-Regeln

`CHANGELOG.md` ist Anwendertext (Sie-Form) und wird mit jedem Paket ausgeliefert. Aufbau:

```
# Änderungen

<Einleitung>

## Unveröffentlicht

- Punkt, der mit der nächsten Freigabe ausgeliefert wird

## 1.2.0 (28.09.2026)

- Punkt
```

**Jede Phase mit kundensichtbarer Änderung ergänzt den Abschnitt „## Unveröffentlicht"** um ein
bis zwei Sätze aus Sicht des Nutzers, direkt bei der Änderung selbst (nicht erst bei der
Freigabe nachträglich zusammensuchen). Regeln für die Einträge:

- Sie-Form, keine Floskeln, das Wichtigste zuerst — dieselben Kundentext-Regeln wie die übrige
  Kunden-Doku.
- **Keine Phasen-Nummern** (P2-51, Phase 90 … sind interne Referenzen, keine Kundeninfo) und
  **keine Firmennamen** aus deinem Bewerbungsverlauf.
- Eine Stelle, kein Changelog für interne Umbauten (Refactorings, Testabdeckung, Kommentare) —
  nur was ein Kunde tatsächlich merkt.

`pipeline/changelog.py` ist die einzige Stelle, die das Format kennt: `version_tupel(s)`,
`abschnitte(text)`, `abschnitt(text, version | None)`, `pruefen(text)` (Formfehler als Liste,
leer = in Ordnung), `freigeben(text, version, datum)` (macht aus „Unveröffentlicht" den
Versionsabschnitt und legt einen neuen leeren „Unveröffentlicht"-Abschnitt an). Dieselbe API liest
auch `app/version.py` für die Programmversion-Karte in den Einstellungen — ein falsch formatierter
Abschnitt fällt dort nicht auf, sondern erst bei der nächsten Freigabe (`freigeben` verweigert
dann mit einer genauen Meldung, welche Kopfzeile nicht passt).

## Ablauf einer Freigabe

**1. Probelauf.** Zeigt die geplante Version, den entstehenden CHANGELOG-Abschnitt und das Tag,
ändert nichts:

```sh
scripts/release.sh freigeben patch --probe
```

Läuft VOR jeder Änderung eine ganze Reihe Prüfungen, jede mit eigener Meldung bei Ablehnung:
Branch `main`; kein geänderter, versionierter Arbeitsbaum (unversionierte Dateien sind nur ein
Hinweis, kein Abbruch); `git fetch origin` und HEAD == `origin/main`; ein abgeschlossener,
erfolgreicher CI-Lauf (`ci.yml`) für exakt diesen Commit (`gh run list --commit <volle SHA>`);
die neue Version größer als `VERSION`; das Tag `vX.Y.Z` existiert weder lokal noch auf `origin`;
`CHANGELOG.md` formgerecht und „Unveröffentlicht" nicht leer; die Kundenpaket-Prüfung für HEAD
ohne Funde (läuft bei dir lokal automatisch MIT der Firmennamen-Regel, s. u. — in der CI fehlt die
lokale Datenbank, dort läuft die Prüfung entsprechend ohne diese eine Regel).

**2. Echte Freigabe.** Dieselben Prüfungen, danach schreibt das Werkzeug `VERSION` und
`CHANGELOG.md`, committet „Release X.Y.Z", legt das annotierte Tag `vX.Y.Z` an (Nachricht =
Versionstext + der CHANGELOG-Abschnitt) und pusht erst `main`, dann das Tag:

```sh
scripts/release.sh freigeben patch
```

Der Push geht ins Entwicklungs-Repo (`origin`). Die Schlussmeldung nennt den nächsten Schritt:
`scripts/veroeffentlichen.sh --ziel <Arbeitskopie> --ref vX.Y.Z`. Ein Release entsteht dort nicht (s. „Zwei
Repositories“).

Scheitert ein Schritt NACH dem Commit (Netzwerk, Tag existiert doch schon, Push abgelehnt), nimmt
das Werkzeug **nichts automatisch zurück** — das könnte Objekte löschen, die anderswo schon
gefetcht wurden. Es druckt stattdessen die genauen `git`-Befehle, mit denen du von Hand
fortsetzt.

**3. Die CI baut das Kundenpaket (im öffentlichen Repo).** Der Tag-Push im öffentlichen Repo
(Abschnitt „Veröffentlichen“) löst `.github/workflows/release.yml` aus; im Entwicklungs-Repo bleiben beide
Jobs übersprungen. Job `tests` ruft `ci.yml` als kompletten Testlauf gegen genau diesen Stand auf (`secret-scan` läuft
dabei bewusst nicht noch einmal — der Commit wurde beim Push auf `main` schon gescannt, und ein
Tag-Push liefert der gitleaks-Action ohnehin keine Commit-Liste). Job `paket` baut danach mit
`python -m pipeline.kundenpaket --ref HEAD --ziel-ordner …` das ZIP, erzeugt eine `.sha256`-Datei
(Format von `sha256sum`), holt die Release-Notizen über `pipeline.release notizen` und
veröffentlicht ein GitHub-Release `vX.Y.Z` mit ZIP, Prüfsumme und den beiden Installationsanleitungen
(`BMS_Install_MAC.md`, `BMS_Install_Windows.md` aus dem Checkout; fehlt eine, schlägt der Schritt fehl) als
Anhang. Fortschritt siehst du auf der Actions-Seite des öffentlichen Repos. **Mit diesem Release ist die
Version veröffentlicht.**

**4. Paket abholen (optional).** Das Release ist schon die Veröffentlichung; abholen brauchst du nur,
um das Paket selbst zu prüfen (etwa für die Update-Probe unten) oder als ZIP weiterzugeben. Sobald das
Release grün ist:

```sh
scripts/release.sh abholen 1.1.0
```

Lädt die Anhänge des Releases `v1.1.0` aus dem öffentlichen Repo (`gh release download --repo …`, nicht
aus dem Entwicklungs-Repo) nach `outputs/kundenpaket/` (Override mit `--ziel DIR`), prüft `BMS_1.1.0.zip`
gegen `BMS_1.1.0.zip.sha256` und nennt den Pfad.

**5. Mehr ist nicht zu tun.** Es gibt keinen Server, auf den ein Paket gelegt wird. Update-Knopf und
Update-Werkzeug finden die Version über `releases/latest` des Repos `holgerdaube/BewerbungsMgmtSystem`
(GitHub liefert dort nur veröffentlichte Releases, keine Entwürfe und Vorabversionen):

- **Knopf „Nach Updates suchen“** (Einstellungen, Karte „Programmversion“): `GET /api/version/neueste`
  in `app/update_pruefen.py`, zeigt Version, Datum und die Release-Notizen (Text aus `CHANGELOG.md`, nur
  „- “-Zeilen bleiben erhalten). Er spielt nichts ein.
- **Update-Werkzeug** (`update.command`, `update_windows.bat`): lädt `BMS_<Version>.zip` aus dem
  Release und vergleicht es mit dem `digest` des Assets (Fallback: das Asset `BMS_<Version>.zip.sha256`;
  fehlt beides, wird nicht eingespielt).
- **Installationsanleitungen** (`BMS_Install_MAC.md`, `BMS_Install_Windows.md`): fragen zuerst
  `releases/latest` (Schritt 4a) und laden dann `releases/download/vVERSION/BMS_VERSION.zip`; `VERSION`
  liest Claude aus `tag_name` der Auskunft. Prüfsumme: das `digest` des Assets (Schritt 4c). Die
  Anleitungen selbst lädt der Anwender als Anhang des Releases (README, Schritt 1); darum hängt
  `release.yml` sie an.

Die Namen `BMS_<Version>.zip` und `BMS_<Version>.zip.sha256` muss `release.yml` genau so erzeugen,
sonst finden Knopf und Werkzeug das Paket nicht. Ändere an Dateinamen im Workflow nichts, ohne
`scripts/bms_update.py` und die Anleitungen mitzuziehen.

**Vertrauensanker ist dein GitHub-Konto.** Wer es übernimmt, könnte ein Release mit fremdem Code
veröffentlichen; `digest` und Manifest kämen dann vom selben Ort. Schutz: Zwei-Faktor-Anmeldung und
Releases nur über `release.yml`, nie von Hand hochgeladene Pakete.

**Alte Installationen bis 1.7.0** fragen weiter den früheren Paketdienst und erfahren dort nie von 2.0.0.
Ein Brückenpaket gibt es nicht: Sie bekommen 2.0.0 einmal als ZIP-Datei im Download-Ordner (von der
Release-Seite) und aktualisieren sich danach selbst.

## Kurzprüfung Mehrsprachigkeit

Vor jeder Freigabe, zusätzlich zur Probe: `scripts/test.sh` und CI grün, `scripts/uebersetzung.sh --pruefen --alle` ohne
Fund, `backend/tests/abnahme/design_vergleich.py` für Deutsch gegen die letzte Freigabe, dazu in einer Probe-Kopie der
erste Start auf Englisch, der Rundgang über alle Seiten und eine Kette `firma-pruefen` bis `anschreiben-erstellen`.
`veroeffentlichen.sh --pruefen` läuft erst auf `main`. Beschreibung und Topics des öffentlichen Repos sind englisch.

## Probebau

Um den Release-Workflow selbst zu prüfen, ohne ein echtes Release zu erzeugen (z. B. nach einer
Änderung an `kundenpaket.py`, `release.py` oder `release.yml`, oder einmalig vor der allerersten
echten Freigabe): `workflow_dispatch` auf `release.yml`, mit einer optionalen `ref` (leer = der
aktuelle Stand von `main`). Läuft dieselben zwei Jobs (`tests` + `paket`), auch im Entwicklungs-Repo,
aber ohne Tag und ohne GitHub-Release — das fertige ZIP samt Prüfsumme landet stattdessen als
Workflow-Artefakt:

```sh
gh workflow run release.yml
gh workflow run release.yml -f ref=<commit-oder-branch>
```

## Update vor der Verteilung testen

Bevor ein Anwender ein Update tatsächlich bekommt, lohnt sich ein Trockenlauf mit dem echten
Update-Werkzeug, nicht nur die Testsuite: eine ältere Version in einem Wegwerf-Ordner installieren
(eigener Port, damit sie eine vorhandene Installation nicht stört), ein bisschen Testdaten anlegen,
eine Beirats-Persona über die Oberfläche ändern, danach die neue `BMS_<Version>.zip` per
`update.command` einspielen und prüfen: Daten und die geänderte Persona sind noch da, die
Programmversion-Karte zeigt die neue Version, `--zurueck` macht das Update sauber rückgängig. Das ZIP
übergibst du dabei als Pfad: Dann gibt es keinen Kontakt zu GitHub, ohne Pfad und ohne
`--offline` fragt das Werkzeug online an. Genau
dieses Szenario stand als Abnahme-Schritt in der Bau-Spec von P2-51 (Abschnitt „Abnahme", Punkt 6)
und ist der Maßstab für jede künftige Freigabe, die den Update-Mechanismus selbst berührt — bei
einer reinen Funktions-Freigabe ohne Änderung an `bms_update.py`/`kundenpaket.py` genügt die
Testsuite.

## Rücknahme

Ein gepushtes Tag sollte **nie** rückwirkend gelöscht werden, sobald jemand das ZIP schon geladen
haben könnte — das Update-Werkzeug erwartet aufsteigende Versionen, ein nachträglich verändertes
Release würde bei einem Anwender, der es bereits hat, ohnehin nichts mehr bewirken und nur Verwirrung
stiften. Fällt ein Fehler dagegen NACH dem Tag-Push, aber BEVOR jemand das ZIP geladen haben kann
(das Release wird sofort über `releases/latest` angeboten, es bleibt also nur ein kurzes Fenster), auf:

```sh
gh release delete v1.1.0 --repo holgerdaube/BewerbungsMgmtSystem --cleanup-tag --yes
```

löscht das GitHub-Release samt Tag im öffentlichen Repo (das Tag im Entwicklungs-Repo bleibt, ebenso der
Commit „BMS 1.1.0“ im öffentlichen Repo). Fehler im Entwicklungs-Repo beheben, danach mit neuer Versionsnummer
freigeben und veröffentlichen (Abschnitt „Veröffentlichen“): Das öffentliche Repo bekommt einen weiteren
Commit.

Ist das ZIP schon geladen oder eingespielt, gilt stattdessen: keinen Tag löschen, sondern einen neuen
Patch mit der Korrektur freigeben. Das Update-Werkzeug beim Anwender spielt die Korrektur wie jedes
andere Update ein.

**Version nicht mehr anbieten.** Soll eine fehlerhafte Version nicht weiter angeboten werden, setzt du
das Release auf GitHub auf „Entwurf“ (Release bearbeiten, oder
`gh release edit v1.1.0 --repo holgerdaube/BewerbungsMgmtSystem --draft`).
`releases/latest` liefert nur veröffentlichte Releases, Knopf und Werkzeug bieten dann wieder die
Vorversion an. Das ist nicht erprobt; probiere es vor dem Ernstfall an einem Test-Release in einem
eigenen Probe-Repo aus. Wer die fehlerhafte Version schon geladen oder eingespielt hat, behält sie. Für
ihn gilt der neue Patch von oben.

## Kundenpaket bauen

Ein Kundenpaket ist ein ZIP mit dem Auslieferungsstand einer Revision — ohne Entwicklungsdateien und ohne
persönliche Daten, mit ein paar neutralisierten Dateien (`README.md`, `config/profil_struktur.md`,
`automation/agent_settings.json`) plus einem Manifest `bms_manifest.json` (Pfad → SHA-256 jeder
ausgelieferten Datei, Version, ob es eine Freigabe ist):

```sh
scripts/kundenpaket.sh
```

Das Skript baut aus dem letzten Commit (`HEAD`), wendet die Ausschluss- und Ersetzungsregeln an, prüft das
Ergebnis danach auf Personendaten — findet die Prüfung auch nur eine Stelle, entsteht **kein** ZIP
(fail-closed) — und legt das fertige Paket unter `outputs/kundenpaket/` ab (gitignored, wie der Rest von
`outputs/`). Der Dateiname trägt die Version (`BMS_1.1.0.zip` bei einer Freigabe, sonst zusätzlich Datum und
Kurz-SHA).

- `--pruefen` — nur prüfen und die Funde ausgeben, ohne ein ZIP zu schreiben.
- `--arbeitsbaum` — Quelle ist der aktuelle Arbeitsbaum statt `HEAD` (Vorschau vor dem nächsten Commit,
  einschließlich neuer, noch nicht hinzugefügter Dateien; auch die Testsuite prüft so). Ergibt
  `BMS_VORSCHAU_<Datum>.zip`.
- `--ziel-ordner DIR` / `--ref REF` — anderer Zielordner bzw. andere Revision.

Liegt `data/bewerbung.sqlite` lokal vor, läuft zusätzlich die Firmennamen-Regel mit — in der CI ohne
Datenbestand fehlt sie entsprechend, die Ausgabe sagt das.

**Kundenpakete entstehen ausschließlich über dieses Skript** — nie den Projektordner kopieren und nie eine
GitHub-Einladung in das Entwicklungs-Repository aussprechen: beides würde persönliche Daten und die
Entwicklungshistorie mitgeben.

## Kundenpaket-Prüfregeln

`pipeline/kundenpaket.py` baut jedes Paket fail-closed: Ein Fund bedeutet **kein** ZIP, egal wie
klein. Die Regeln selbst stehen in `pipeline/personendaten.py`; dasselbe Modul prüft den Export für das
öffentliche Repo (Abschnitt „Veröffentlichen“). Geprüft werden alle ausgelieferten Textdateien auf:

- **Anschrift**, **Private Kontaktdaten**, **Dritte Personen** und **Name des Nutzers**. Ihre Muster stehen
  nicht im Code, sondern kommen aus lokalen Quellen (Abschnitt „Prüfmuster“ unten).
- **E-Mail-Adressen** (außer den Domains in `ERLAUBTE_DOMAINS`, den für Beispiele reservierten Endungen
  `.example`/`.invalid`/`.test`/`.localhost` und den einzelnen Adressen in `ERLAUBTE_ADRESSEN`),
  **Telefonnummern** (außer der einen Beispielnummer in `BMS_Install_MAC.md` und
  `BMS_Install_Windows.md`).
- Im Umfang „paket“ (Kundenpaket) gilt der Name des Nutzers nur an drei Stellen, jeweils mit eigenem
  Regelnamen: **„Name des Nutzers in Kundentexten“** (Doku/Oberfläche/Skills, s. `NAME_KUNDENTEXT_PFADE`),
  **„Name des Nutzers im Python-Programmtext“** (String-Literale, Docstrings ausgenommen) und
  **„Name des Nutzers im TS/TSX-Programmtext“** (Code ohne Kommentare). Im Umfang „oeffentlich“ (Export)
  gilt stattdessen die eine Regel **„Name des Nutzers“**: überall, auch in Kommentaren und Docstrings.
- **Bestands-IDs** — in JEDER ausgelieferten Textdatei: jedes Muster
  „Job/Jobs/Task/Tasks/Mail/Mails/Lauf/Bewerbung/Firma + mindestens zwei Ziffern".
- **Firmennamen aus dem Bewerbungsverlauf der Installation** (NUR lokal gegen die echte
  `data/bewerbung.sqlite`, rein lesend): Firmennamen aus `company`/`job`/`targetcompany`/
  `headhunter` werden auf ihre Kernform reduziert (Rechtsform abgetrennt) und
  groß-/kleinschreibungsgenau als ganzes Wort gesucht. `ERLAUBTE_FIRMENNAMEN` nimmt funktionale
  Nennungen aus (Portale, ATS, Infrastruktur wie LinkedIn, Workday, Google …), je Eintrag mit
  Begründung im Code. In der CI (kein Datenbestand im Checkout) läuft diese eine Regel nicht mit —
  die Ausgabe sagt das ausdrücklich.
- **Zeilenenden**: `.bat`-Dateien brauchen CRLF, `.command`/`.sh`/`.py` dürfen kein CR enthalten.

Dazu zwei paketweite Regeln: **Pflichtdateien fehlen** und **Import eines ausgeschlossenen
Moduls** (ein ausgeliefertes `.py` importiert etwas, das beim Ausschließen weggefallen ist), sowie
seit P2-51 **Startdatei nicht ausführbar** (`update.command` zählt hier mit).

**Eine Ausnahme je Pfad** (`_FREMDER_WORTLAUT`, P2-77): In `frontend/src/rechtliches/drittlizenzen_texte.txt`
entfallen genau die Regeln „E-Mail-Adressen“, „Firmennamen“ und (beim Export) der Name des Nutzers, weil der
Wortlaut fremder Lizenzen mit Autoren-Adressen und Copyright-Zeilen nicht verändert werden darf; alle übrigen
Regeln gelten dort weiter.

### Prüfmuster: nur aus lokalen Quellen

Im Code stehen weder Anschrift noch Mailadresse noch Namen. `personendaten.muster_laden` baut die Muster
zur Laufzeit aus:

1. `config/profil.md` (nicht im Git), gelesen mit dem Parser der App (`pipeline/profil_datei.py`): Name,
   Standort als Anschrift (daraus Straße und Postleitzahl als eigene Muster), Kontakt (E-Mail, Telefon)
   und LinkedIn-Profil.
2. der lokalen Datenbank `data/bewerbung.sqlite`, nur lesend: die Firmennamen (Regel „Firmennamen“) und
   die Namen der Kontakte (Regel „Dritte Personen“).
3. optional `pruefmuster.txt` im Secrets-Ordner (`~/.bewerbung_mgmt_secrets/`, Override
   `BMS_SECRETS_DIR`): je Zeile ein Begriff, `#` am Zeilenanfang = Kommentar. Für frühere Anschriften und
   Namen, die nirgends sonst stehen. Der Begriff wird nach seiner Form einer Regel zugeordnet: mit `@`,
   `linkedin.` oder `://` = Private Kontaktdaten, mit Ziffer oder Straßen-Endung = Anschrift, alles
   andere = Dritte Personen.

Fehlen Profil oder Datenbank (etwa in der CI), entfallen die persönlichen Regeln still; die allgemeinen
(E-Mail mit Ausnahmen, Telefonformat, Bestands-IDs, absolute Benutzerpfade) laufen weiter, und die Ausgabe
sagt, was fehlte. Das Export-Werkzeug bricht in diesem Fall ab. Kein Fund und keine Testausgabe zeigt ein
Muster; Funde nennen Datei, Zeile und Regel mit einem gekürzten Ausschnitt der Datei.

**Der Name des Autors** gilt als ganzes Wort überall als Fund, außer in der Zuschreibungsliste (`NOTICE`,
`LICENSE`, `frontend/src/rechtliches/ueber.md`, `ueber.en.md` und die Abschnitte zu Autor und Lizenz in `README.md` und `README.de.md`).
„Daube.Tech“ zählt nicht als Nachname, und `holgerdaube/BewerbungsMgmtSystem` ist die einzig erlaubte Form
des Kontonamens.

**Bei einem Fund:** nie das ZIP von Hand nachbearbeiten. Die Ursache im echten Quelltext beheben
(Kommentar/Beispiel neutralisieren, oder falls es sich um eine legitime funktionale Nennung
handelt, den Eintrag mit Begründung in die passende Ausnahmeliste aufnehmen —
`ERLAUBTE_DOMAINS`/`ERLAUBTE_ADRESSEN`/`ERLAUBTE_FIRMENNAMEN`/`_PERSONA_PFADE` in
`pipeline/personendaten.py`, je nachdem welche Regel angeschlagen hat), dann lokal erneut prüfen, bevor du
überhaupt an `freigeben` denkst. In Tests gehören erfundene Werte hinein (`beispiel.de`, `example.org`,
`*.example`); trägt eine echte Anbieter-Domain die Testlogik (Erkennung von Freemail, Portal- oder
ATS-Absendern), kommt nur die einzelne Testadresse in `ERLAUBTE_ADRESSEN`, nie eine ganze Freemail-Domain:

```sh
cd backend && ~/.bewerbung_mgmt_venv/bin/python -m pipeline.kundenpaket --arbeitsbaum --pruefen
```

`--arbeitsbaum` prüft den aktuellen Stand (auch unversionierte, neue Dateien), noch bevor du
committest — die Firmennamen-Regel läuft dabei automatisch mit, sobald `data/bewerbung.sqlite`
lokal existiert.


## Veröffentlichen

Das öffentliche Repo `holgerdaube/BewerbungsMgmtSystem` bekommt nie die Historie des Entwicklungs-Repositorys,
sondern je Version einen geprüften Stand als **einen** Commit „BMS X.Y.Z“ mit dem Tag `vX.Y.Z`. Entwickelt
wird weiter im Entwicklungs-Repo; im öffentlichen Repo ändert sich nur etwas bei einer Freigabe.
`scripts/veroeffentlichen.sh` (ruft `python -m pipeline.veroeffentlichung`) erzeugt den Stand in einer
lokalen Arbeitskopie des öffentlichen Repos:

```sh
scripts/veroeffentlichen.sh --ziel <Arbeitskopie des öffentlichen Repos> [--ref <Commit>] [--pruefen]
```

Ablauf des Werkzeugs:

1. `--ref` (Vorgabe `HEAD`) muss in `main` enthalten sein. Bei `HEAD` mit ungesicherten Änderungen warnt das
   Werkzeug: Exportiert wird der Commit, nicht der Arbeitsbaum.
2. Die Einträge kommen per `git archive` aus dem Commit (wie beim Paketbau), abzüglich der kurzen
   Ausschlussliste `NICHT_OEFFENTLICH` (`tasks/`, `.claude/launch.json`). Es gibt keinen zweiten,
   getrennt gepflegten Baum und keine Ersatzdateien beim Export: Was öffentlich nicht stehen darf, wird im
   Entwicklungs-Repo bereinigt.
3. Die Prüfung nutzt die Regeln von `pipeline/personendaten.py` im Umfang „oeffentlich“ (alle Dateien, keine
   Pfad-Ausnahmen außer dem fremden Wortlaut und der Zuschreibungsliste) mit den lokalen Prüfmustern von oben,
   dazu eine schnelle Suche nach Geheimnissen (API-Schlüssel, GitHub-Token, OAuth-Client-Geheimnisse,
   private Schlüssel). Fehlen Profil oder Datenbank, bricht das Werkzeug ab: „Ohne Profil und Datenbank
   lässt sich nicht prüfen, ob persönliche Daten im Export stehen.“ Jeder Fund wird wie bei der
   Paketprüfung ausgegeben (Datei, Zeile, Regel, gekürzter Ausschnitt), das Ergebnis ist Exit-Code 1, und
   es wird nichts geschrieben.
4. `--pruefen` endet hier.
5. Das Ziel muss ein Ordner mit `.git` sein, dessen `origin` auf `github.com/holgerdaube/BewerbungsMgmtSystem`
   zeigt (https oder ssh), ohne ungesicherte Änderungen und mit einer GitHub-noreply-Adresse als
   Commit-Identität (Abschnitt „Einmalig“ unten). Sonst bricht das Werkzeug ab, ohne etwas zu schreiben.
6. Spiegeln: Alle Dateien im Ziel außer `.git/` werden gelöscht, die Einträge mit ihren Rechten
   (ausführbar ja/nein) geschrieben. Im Entwicklungs-Repo gelöschte Dateien verschwinden so auch im Ziel.
7. Ausgabe: die Zahl der Dateien, `git status --short` des Ziels (gekürzt) und die nächsten Schritte mit
   echtem Ziel und echter Version: durchsehen, committen, `main` pushen, CI abwarten, taggen, Tag pushen,
   Release prüfen (die Befehle aus „Je Version“ unten).

**Das Werkzeug committet und pusht nie.** Commit, Tag und Push macht der Ablauf „Je Version“ von Hand.

### Einmalig: Konto, Arbeitskopie und Commit-Identität

Ohne diese Einrichtung stünde deine private Mailadresse in jedem öffentlichen Commit und Tag. Darum prüft
`veroeffentlichen.sh` sie vor dem Spiegeln und bricht sonst ab.

**Konto** (GitHub → Settings → Emails): „Keep my email addresses private“ einschalten und im Profil keine
öffentliche Mailadresse zeigen. „Block command line pushes that expose my email“ nicht einschalten: GitHub
lehnte sonst auch Pushes ins Entwicklungs-Repo ab, dessen Commits die private Adresse tragen.

**Arbeitskopie klonen**, außerhalb eines iCloud-Ordners (sie lässt sich jederzeit neu klonen):

```sh
git clone https://github.com/holgerdaube/BewerbungsMgmtSystem <Arbeitskopie>
```

**Identität setzen**, nur in der Arbeitskopie (im Entwicklungs-Repo bleibt es bei deiner üblichen Adresse),
und kontrollieren:

```sh
git -C <Arbeitskopie> config user.name "<Anzeigename>"
git -C <Arbeitskopie> config user.email <ID>+<Konto>@users.noreply.github.com
git -C <Arbeitskopie> config user.email
```

`<ID>` ist die Kontonummer (`gh api user --jq .id`), `<Konto>` der Kontoname. Der letzte Befehl zeigt die
gesetzte Adresse.

Geprüft wird die **wirksame** Identität, so wie `git commit` und `git tag` sie verwenden
(`git var GIT_AUTHOR_IDENT` und `GIT_COMMITTER_IDENT`): lokale und globale Konfiguration und die
Umgebungsvariablen `GIT_AUTHOR_EMAIL`, `GIT_COMMITTER_EMAIL` und `EMAIL`, die der Einstellung vorgehen.
Beide Adressen müssen `<ID>+<Konto>@users.noreply.github.com` oder `<Konto>@users.noreply.github.com`
entsprechen. Dazu müssen alle vorhandenen Commits (Autor und Committer, alle Zweige) und annotierten Tags
(Tagger) eine noreply-Adresse tragen oder eine der eigenen Adressen von GitHub (die allgemeine
Absenderadresse für Commits aus der Weboberfläche, die Bot-Form von Dependabot und Co.). Ein leeres Repo
besteht diese Prüfung.

- „Die Commit-Adresse der Arbeitskopie ist keine GitHub-noreply-Adresse“: Adresse wie oben setzen. Steht eine
  Umgebungsvariable dahinter, nennt die Meldung ihren Namen; sie ist zu entfernen.
- „Ein Commit oder Tag im Ziel trägt eine andere Adresse als die GitHub-noreply-Adresse“: der Verlauf der
  Arbeitskopie ist belastet. Arbeitskopie neu klonen; steht die Adresse schon im Verlauf auf GitHub, das Repo
  löschen und neu anlegen (Abschnitt „Das erste Mal“).

Beide Meldungen nennen die gefundene Adresse nie.

### Je Version

```sh
scripts/release.sh freigeben <Stufe>
scripts/veroeffentlichen.sh --ziel <Arbeitskopie> --ref vX.Y.Z
git -C <Arbeitskopie> add -A
git -C <Arbeitskopie> commit -s -m "BMS X.Y.Z"
git -C <Arbeitskopie> push origin main
# … CI im öffentlichen Repo abwarten, sie muss grün sein …
git -C <Arbeitskopie> tag -a vX.Y.Z -m "BMS X.Y.Z"
git -C <Arbeitskopie> push origin vX.Y.Z
scripts/release.sh abholen X.Y.Z
```

1. `freigeben` im Entwicklungs-Repo (Abschnitt „Ablauf einer Freigabe“): Version, CHANGELOG, Commit, Tag,
   Push. Es entsteht kein Release.
2. `veroeffentlichen.sh --ref vX.Y.Z` exportiert genau den freigegebenen Stand in die Arbeitskopie. Mit
   `git -C <Arbeitskopie> status` und `diff` durchsehen, was sich gegenüber der letzten Version ändert.
3. Ein Commit mit `-s` (fügt „Signed-off-by“ mit der noreply-Adresse hinzu), Nachricht „BMS X.Y.Z“.
4. Erst `main` pushen und die CI abwarten: `ci.yml` testet den Stand, bevor ein Tag das Release auslöst.
5. Dann das annotierte Tag setzen und pushen. Der Tag-Push startet `release.yml` im öffentlichen Repo: Test,
   Paketbau, Release mit ZIP, Prüfsumme und beiden Installationsanleitungen.
6. Das Release prüfen: `scripts/release.sh abholen X.Y.Z` lädt aus dem öffentlichen Repo und vergleicht die
   Prüfsumme. Auf GitHub zeigt die Release-Seite die Notizen aus dem CHANGELOG und vier Anhänge.

### Beiträge Dritter

Ein Pull Request wird **nie im öffentlichen Repo gemergt**: Der nächste Export überschriebe ihn. Er läuft über
das Entwicklungs-Repo:

1. Als Patch ins Entwicklungs-Repo übernehmen:
   `gh pr diff <Nr> --repo holgerdaube/BewerbungsMgmtSystem | git apply`.
2. Mit den Trailern `Co-authored-by` und `Signed-off-by` des Beitragenden committen (Name und Adresse stehen
   im Pull Request).
3. Der Beitrag erscheint mit der nächsten Version. Den Pull Request mit einem Hinweis darauf schließen
   (`gh pr close <Nr> --repo holgerdaube/BewerbungsMgmtSystem --comment "…"`).

### Das erste Mal

Das Repo wird zuerst **privat** angelegt und mit dem Ablauf oben gefüllt (Export, Commit, CI, Tag, Release).
Dann folgt die Durchsicht auf GitHub: Startseite, Dateiliste (kein `tasks/`), Release mit allen Anhängen,
Actions, und in der Commit-Ansicht die `.patch`-Datei (die Zeile „From“ nennt nur die noreply-Adresse). Ist
etwas durchgerutscht, wird das Repo gelöscht und neu angelegt, nicht nachgebessert: Release,
Actions-Protokolle und Tags behielten den alten Stand. Erst danach wird es öffentlich geschaltet; danach
lässt sich nichts zurückholen.

Beim Umschalten kommen die Sicherheitsfunktionen dazu, die es für private Repos des kostenlosen Plans nicht
oder nur eingeschränkt gibt: private Sicherheitsmeldung (`SECURITY.md` verweist darauf),
Dependabot-Warnungen, Secret Scanning mit Push-Schutz, ein Ruleset für `main` (kein Force-Push, kein
Löschen) und eines für die Tags `v*` (kein Verschieben, kein Löschen), Workflow-Rechte nur lesend und die
Freigabe von Workflow-Läufen für alle externen Beitragenden. Wiki und Projects bleiben aus, Issues an.

**Ehrliche Grenze:** Die Prüfung findet nur, was sie kennt. Profil, Datenbank und `pruefmuster.txt` decken die
heutigen Daten ab; ein Name, der nirgends steht, rutscht durch. Deshalb bleibt die Durchsicht des Exports vor
dem ersten Umschalten des Repos auf öffentlich Pflicht.
