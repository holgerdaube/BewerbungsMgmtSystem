# Hinweise für Läufe mit ChatGPT (Codex)

Das BMS startet Codex für seine KI-Läufe. Die Skills unter `.agents/skills` sind eine Kopie von `.claude/skills` und
nennen die Werkzeuge von Claude Code. Übersetze ihre Namen:

- WebSearch: deine Websuche. WebFetch: eine Webseite über deine Websuche öffnen.
- Write, Read, Edit: Dateien im Projekt lesen und schreiben, per Shell.
- Unteragenten (Task, Subagent): Starte sie, wenn du kannst. Sonst erledige die Teile nacheinander selbst. Eine
  vorgeschriebene Vier-Augen-Prüfung machst du dann als eigenen, frischen zweiten Durchgang über die Treffer.
- Einen anderen Skill aufrufen: dessen `SKILL.md` unter `.agents/skills` lesen und befolgen. `anthropic-skills:…` gibt
  es hier nicht.

Arbeite nur in diesem Projektordner. Frage nie nach, du läufst ohne Benutzer. Fehlt eine im Skill genannte optionale
Datei (etwa `config/zielfirmen.md`), mache ohne sie weiter und nenne das in der Abschlussmeldung.
