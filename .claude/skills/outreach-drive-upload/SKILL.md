---
name: outreach-drive-upload
description: Lädt den aktuellen Outreach-Tracker-Stand format-getreu zurück nach Google Drive. Nutze diesen Skill, wenn der Nutzer sinngemäß sagt "lad den Outreach-Tracker hoch", "push nach Drive", "aktualisiere die Drive-Datei", "Rück-Upload".
---

# Outreach-Tracker → Google Drive

Baut die Outreach-Datei aus dem aktuellen DB-Stand (format-erhaltend) und lädt sie nach Google Drive.

## Wichtige Einschränkungen
1. **Kein Update-in-place.** Die bestehende Datei (`..._<Name>.xlsx`, ID
   `[DRIVE_DATEI_ID]` — pro Installation in diesem Skill eintragen) kann NICHT überschrieben werden — nur eine neue Datei anlegen.
   Kein Lösch-/Papierkorb-Tool → bei häufigem Upload sammeln sich Kopien. Nur auf Zuruf, datierte Namen.
2. **⛔ AKTUELL NICHT AUTOMATISIERBAR (getestet 09.07.):** `create_file` verlangt die base64 INLINE als
   Argument. Die fertige .xlsx ist ~75 KB → ~100 KB base64 und überschreitet das Tool-Argument-Limit
   (dieselbe Grenze, die den Download in eine Datei auslagert). Der String lässt sich nicht in den
   Tool-Call bekommen → Upload schlägt fehl. **Zuverlässiger Weg stattdessen:** in der App den Button
   „⬇ Outreach-Tracker (Original-Format)" klicken und die Datei manuell in den Drive-Ordner ziehen
   (Format ist bereits korrekt). Erst wieder versuchen, wenn der Drive-Connector Datei-/Streaming-Upload
   unterstützt oder die Datei klein genug ist.

## Ablauf
1. Aktuellen Stand format-getreu bauen:
   ```sh
   cd backend && ~/.bewerbung_mgmt_venv/bin/python -m pipeline.export_outreach
   ```
   Ergebnis: `data/exports/JJJJ_Job_Search_Tracker_<Name>.xlsx` (nur das Jahr im Namen, kein Tag, z. B. `2026_Job_Search_Tracker_...`; der Export spiegelt immer den aktuellen Gesamtstand).
2. Datei base64-kodieren:
   ```sh
   base64 -i "<pfad zur .xlsx>"
   ```
3. Nach Drive hochladen mit dem Drive-MCP `create_file`:
   - `base64Content`: der base64-String aus Schritt 2
   - `title`: `JJJJ_Job_Search_Tracker_<Name>.xlsx` (derselbe Name wie die lokale Datei)
   - `parentId`: `[DRIVE_ORDNER_ID]` (pro Installation in diesem Skill eintragen — derselbe Ordner wie das Original)
   - `contentMimeType`: `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`
   - `disableConversionToGoogleType`: `true`  ← ZWINGEND, sonst wird zu Google Sheets konvertiert und das Format geht verloren
4. Die zurückgegebene `viewUrl` an den Nutzer melden.

## Grenzen / Sicherheit
- **Ausgehende Aktion in einen mit Dritten geteilten Ordner** → immer erst die Bestätigung des Nutzers einholen,
  bevor hochgeladen wird.
- Format bleibt erhalten (nur Datenzeilen ersetzt, siehe `pipeline/export_outreach.py`).
- Kein Überschreiben des Originals möglich (siehe Einschränkung oben).
