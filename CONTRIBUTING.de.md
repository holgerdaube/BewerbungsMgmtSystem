# Mitmachen

[English](CONTRIBUTING.md) · **Deutsch**

Schön, dass Sie am Bewerbungs-Management-System (BMS) mitarbeiten möchten. Diese Seite fasst die Regeln
für Beiträge zusammen. Wenn Sie nur einen Fehler gefunden haben, genügt ein Issue:
https://github.com/holgerdaube/BewerbungsMgmtSystem/issues. Eine **Sicherheitslücke** melden Sie bitte
nicht dort, sondern wie in [`SECURITY.de.md`](SECURITY.de.md) beschrieben.

## Lizenz und Herkunftsnachweis (DCO)

Das BMS steht unter der Apache License 2.0 (`LICENSE`). Ein Beitrag, den Sie einreichen, steht unter
derselben Lizenz (Abschnitt 5 der Lizenz).

Zusätzlich verlangt das Projekt den **Developer Certificate of Origin** (DCO, Version 1.1,
https://developercertificate.org). Mit ihm bestätigen Sie, dass Sie den Beitrag selbst geschrieben haben
oder das Recht haben, ihn unter dieser Lizenz einzureichen. Das tun Sie, indem Sie jeden Commit mit
`-s` signieren:

```sh
git commit -s -m "Kurze Beschreibung der Änderung"
```

Git hängt dann die Zeile `Signed-off-by: Ihr Name <ihre@adresse>` an die Commit-Nachricht an. Name und
Adresse stammen aus `git config user.name` und `git config user.email`. Wollen Sie Ihre private
Mailadresse nicht veröffentlichen, verwenden Sie die noreply-Adresse Ihres GitHub-Kontos. Haben Sie das
Signieren vergessen, hilft `git commit --amend -s` für den letzten Commit; bei mehreren Commits
`git rebase --signoff`.

## Entwicklung einrichten

Wie Sie den Quellcode einrichten (Python-Umgebung, Oberfläche bauen, Start), steht unter macOS und Windows
in [`docs/INSTALLATION.md`](docs/INSTALLATION.md). Aufbau, Datenmodell und Konventionen beschreibt
[`docs/DOKUMENTATION.md`](docs/DOKUMENTATION.md). Lesen Sie dort vor einer größeren Änderung die
Abschnitte „Grundprinzipien“ und „Tests & CI“.

## Sprache

- **Oberfläche:** Texte stehen immer in beiden Sprachen (`frontend/src/i18n/de` und `en`, im Backend `tx()`). Die
  CI prüft das.
- **Anwender-Dokumentation:** Englisch und Deutsch im selben Commit, bestätigt mit
  `scripts/uebersetzung.sh --bestaetigen <englische Datei>`.
- **Terminal:** Meldungen der Werkzeuge in `scripts/`, der Start- und Stoppskripte und des Servers (`tt()`) stehen in beiden Sprachen und folgen der Sprache des Betriebssystems, nicht der Oberfläche.
- **Quelle:** Deutsch ist die Quelle der Dokumentation. Die technische Dokumentation darf bis zur nächsten
  Freigabe nachhängen.
- **Code:** Code-Kommentare, Docstrings, Commit-Nachrichten und Skills sind deutsch. Issues und Pull Requests auf
  Englisch sind willkommen.
- **Anrede und Schreibweise:** Deutsche Texte in der Oberfläche und im `CHANGELOG.md` stehen in der Sie-Form,
  englische Texte in britischem Englisch.

## Tests vor dem Pull Request

Jede Änderung am Verhalten braucht einen Test, und die ganze Suite muss grün sein, bevor Sie den Pull
Request öffnen:

```sh
scripts/test.sh                      # Backend-Tests (einmalig: backend/requirements-dev.txt installieren)
cd frontend && npm run typecheck && npm run build   # wenn Sie die Oberfläche geändert haben
```

Die Tests laufen gegen eine eigene Wegwerf-Datenbank und fassen Ihre echte `data/bewerbung.sqlite` nicht
an. Die CI wiederholt die Prüfung bei jedem Pull Request auf Linux und Windows, dazu Typprüfung, Build
und einen Secret-Scan.

## Keine echten Personendaten

In Code, Tests, Beispielen, Dokumentation und Commit-Nachrichten stehen **keine echten Personendaten und
keine echten Bewerbungsdaten**: keine Namen, Anschriften, Mailadressen oder Telefonnummern realer
Personen, keine Firmennamen, Stellen oder Nummern aus Ihrer eigenen Jobsuche, keine Lebensläufe, keine
Zugangsdaten. Nehmen Sie erfundene Werte: Max Mustermann oder Benno Bewerbaer als Person, Beispiel GmbH oder
Firma A als Firma, Adressen unter `beispiel.de`. Prüfen Sie Ihre Änderung vor dem Einreichen mit
`git diff` auf versehentlich mitgenommene Daten.

## Leitplanken für neue Funktionen

- **Nur für die bewerbende Person.** Das BMS unterstützt ausschließlich die Seite, die sich bewirbt.
  Funktionen, mit denen Arbeitgeber Bewerbende bewerten, sortieren oder auswählen, werden nicht
  aufgenommen (Grundprinzip 8 in `docs/DOKUMENTATION.md`).
- **Der Mensch entscheidet.** Das BMS bewirbt sich nicht selbst und verschickt keine E-Mails, es legt nur
  Entwürfe an (Grundprinzip 1). Ein Sende-Codepfad hat im Projekt keinen Platz, ein Test
  (`test_kein_sendcodepfad.py`) hält das fest.
- **Keine erfundenen Fakten.** KI-Texte arbeiten belegt; was das System nicht weiß, markiert es, statt
  zu raten (Grundprinzip 2).
- **Zwei KI, ein Wortlaut.** Die KI-Läufe gehen wahlweise über Claude Code oder über die Codex CLI
  (ChatGPT). Die Skills in `.claude/skills` sind die einzige Quelle: Das BMS spiegelt sie vor jedem Lauf
  nach `.agents/skills` (nicht versioniert), und `AGENTS.md` übersetzt die Werkzeugnamen. Ändern Sie nie die
  Kopie unter `.agents/skills`, und schreiben Sie Skills so, dass sie unter beiden KI laufen.

## Dokumentation

Die Dokumente in `docs/` sind Markdown-Dateien (`.md`, die Quelle). Zu jeder gehört eine erzeugte
`.html`-Datei zum Drucken und Weitergeben. Nach jeder Änderung an einer `.md` erzeugen Sie die HTML-Fassung
neu und reichen beide Dateien gemeinsam ein:

```sh
scripts/docs_html.sh
```

Ein Test (`backend/tests/test_docs_html.py`) schlägt fehl, wenn eine `.html` fehlt oder veraltet ist.
Änderungen, die Anwender merken, tragen Sie zusätzlich in `CHANGELOG.md` und `CHANGELOG.en.md` unter
„Unveröffentlicht“ ein, in ein bis zwei Sätzen und ohne interne Nummern.

## Pull Request

1. Legen Sie einen Fork an und arbeiten Sie auf einem eigenen Zweig.
2. Halten Sie den Pull Request klein und zu einem Thema. Beschreiben Sie, was sich ändert und warum.
3. Signieren Sie jeden Commit (`git commit -s`), siehe oben.
4. Lassen Sie `scripts/test.sh` laufen und warten Sie die CI ab. Der Pull Request kann erst bei grüner CI
   übernommen werden.
