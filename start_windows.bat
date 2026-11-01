@echo off
setlocal
chcp 65001 >nul
rem Bewerbungs-Management-System unter Windows starten (Doppelklick oder: start_windows.bat).
rem Oeffnet die App im Browser und startet den lokalen Server -- Windows-Pendant zu
rem start.command (macOS): gleiches Verhalten (venv-Check, Server im Vordergrund, Browser nach
rem kurzer Verzoegerung), nur mit den unter Windows ueblichen venv-/Kommandopfaden.
rem Setup/Details: docs\SETUP-WINDOWS.md.

cd /d "%~dp0backend"
set "VENV=%USERPROFILE%\.bewerbung_mgmt_venv\Scripts\python.exe"

if not exist "%VENV%" (
  echo Fehler: venv nicht gefunden unter %USERPROFILE%\.bewerbung_mgmt_venv
  echo Setup siehe docs\SETUP-WINDOWS.md.
  rem pause: bei Doppelklick-Start schliesst sich das Fenster sonst sofort wieder --
  rem ohne pause waere die Fehlermeldung nie lesbar.
  pause
  exit /b 1
)

rem Browser mit kurzer Verzoegerung oeffnen (laeuft im Hintergrund weiter, blockiert den
rem Server-Start nicht) -- PowerShell-Einzeiler statt eines verschachtelten "start"-Aufrufs,
rem um Batch-Anfuehrungszeichen-Fallstricke zu vermeiden. -Command ist NICHT von der
rem PowerShell-Ausfuehrungsrichtlinie betroffen (die gilt nur fuer .ps1-Skriptdateien).
rem Kein -WindowStyle Hidden: Mit /b teilt PowerShell das Konsolenfenster dieser Datei und
rem wuerde damit das Serverfenster verstecken. Ein eigenes Fenster entsteht mit /b ohnehin nicht.
start /b "" powershell -NoProfile -Command "Start-Sleep -Seconds 2; Start-Process 'http://localhost:8000'"

echo Starte Bewerbungs-Management auf http://localhost:8000  (Beenden: Strg+C)
set "PORT=8000"
"%VENV%" run_server.py
rem pause wie oben: Endet der Server mit einem Fehler (Port belegt, Importfehler), schliesst sich
rem das Fenster sonst sofort, und die Meldung waere nie lesbar.
if errorlevel 1 (
  echo.
  echo Der Server wurde mit einem Fehler beendet. Die Meldung steht oben.
  pause
)

endlocal
