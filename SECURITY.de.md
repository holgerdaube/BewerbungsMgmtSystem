# Sicherheitshinweise

[English](SECURITY.md) · **Deutsch**

Das Bewerbungs-Management-System (BMS) läuft lokal auf dem Rechner der Nutzerin oder des Nutzers und
verarbeitet persönliche Daten (Lebenslauf, Bewerbungsverlauf, E-Mails). Sicherheitslücken nehmen wir
deshalb ernst. Danke, wenn Sie uns eine melden.

## Eine Sicherheitslücke melden

Bitte melden Sie Sicherheitslücken **nicht** als öffentliches Issue, in einem Pull Request oder in einer
Diskussion. Nutzen Sie stattdessen die private Sicherheitsmeldung von GitHub:

1. Öffnen Sie https://github.com/holgerdaube/BewerbungsMgmtSystem/security.
2. Wählen Sie **Report a vulnerability** („Sicherheitslücke melden“).
3. Beschreiben Sie das Problem. Die Meldung sehen nur Sie und die Verantwortlichen des Projekts.

Wir bestätigen den Eingang, melden uns mit einer ersten Einschätzung und stimmen mit Ihnen ab, wann ein
Fehler öffentlich beschrieben wird. Eine feste Antwortfrist können wir nicht zusagen.

## Was in die Meldung gehört

- Welche Version betroffen ist (Fuß der Seitenleiste oder Datei `VERSION`) und auf welchem System (macOS
  oder Windows) Sie sie nutzen.
- Was passiert und was Sie erwartet hätten, möglichst mit den Schritten zum Nachstellen.
- Welche Folgen Sie sehen, etwa welche Daten ein Angreifer lesen oder verändern könnte.
- Wenn Sie einen Lösungsvorschlag haben, gern auch den.

**Schicken Sie keine Zugangsdaten und keine echten persönlichen Daten mit:** keine Passwörter, Token,
API-Schlüssel, Lebensläufe, E-Mails oder Datenbankdateien. Schwärzen Sie solche Stellen in Auszügen und
Bildschirmfotos, oder erfinden Sie Beispielwerte, mit denen sich das Problem trotzdem zeigen lässt.

## Unterstützte Versionen

Sicherheitskorrekturen erscheinen nur für die **neueste Version**. Prüfen Sie vor einer Meldung, ob das
Problem dort noch auftritt. Wie Sie aktualisieren, steht in der [README](README.de.md), Abschnitt „Updates“.

## Was nicht dazugehört

Fehler ohne Sicherheitsbezug melden Sie bitte als normales Issue:
https://github.com/holgerdaube/BewerbungsMgmtSystem/issues. Probleme in Diensten, die das BMS nur anbindet
(Claude, ChatGPT, Gmail, Apify, GitHub), melden Sie bitte dem jeweiligen Anbieter.
