@echo off
setlocal
chcp 65001 >nul
rem Terminal-Sprache (P2-95): BMS_TERMINAL_SPRACHE (de/en) gewinnt, sonst die Windows-Anzeigesprache.
rem Beginnt der Wert mit "de", gilt Deutsch, sonst Englisch (auch bei jedem Fehler). Die Variable
rem bleibt gesetzt, damit die Python-Werkzeuge dieselbe Sprache nehmen. Von der Wahl haengt keine
rem Meldung und kein Ablauf ab: Schlaegt die Erkennung fehl, gilt Englisch.
if not defined BMS_TERMINAL_SPRACHE for /f %%L in ('powershell -NoProfile -Command "(Get-UICulture).TwoLetterISOLanguageName" 2^>nul') do set "BMS_TERMINAL_SPRACHE=%%L"
if not defined BMS_TERMINAL_SPRACHE set "BMS_TERMINAL_SPRACHE=en"
if /i "%BMS_TERMINAL_SPRACHE:~0,2%"=="de" (set "BMS_TERMINAL_SPRACHE=de") else (set "BMS_TERMINAL_SPRACHE=en")
rem Bewerbungs-Management-System unter Windows starten (Doppelklick oder: start_windows.bat).
rem Oeffnet die App im Browser und startet den lokalen Server -- Windows-Pendant zu
rem start.command (macOS): gleiches Verhalten (venv-Check, Server im Vordergrund, Browser nach
rem kurzer Verzoegerung), nur mit den unter Windows ueblichen venv-/Kommandopfaden.
rem Setup/Details: docs\SETUP-WINDOWS.md.

cd /d "%~dp0backend"
set "VENV=%USERPROFILE%\.bewerbung_mgmt_venv\Scripts\python.exe"

if not exist "%VENV%" (
  if "%BMS_TERMINAL_SPRACHE%"=="de" (
    echo Fehler: venv nicht gefunden unter %USERPROFILE%\.bewerbung_mgmt_venv
    echo Setup siehe docs\SETUP-WINDOWS.md.
  ) else (
    echo Error: venv not found at %USERPROFILE%\.bewerbung_mgmt_venv
    echo Setup: see docs\en\SETUP-WINDOWS.md.
  )
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

if "%BMS_TERMINAL_SPRACHE%"=="de" (
  echo Starte Bewerbungs-Management auf http://localhost:8000  ^(Beenden: Strg+C^)
) else (
  echo Starting BMS at http://localhost:8000  ^(stop: Ctrl+C^)
)
set "PORT=8000"
"%VENV%" run_server.py
rem pause wie oben: Endet der Server mit einem Fehler (Port belegt, Importfehler), schliesst sich
rem das Fenster sonst sofort, und die Meldung waere nie lesbar.
if errorlevel 1 (
  echo.
  if "%BMS_TERMINAL_SPRACHE%"=="de" (
    echo Der Server wurde mit einem Fehler beendet. Die Meldung steht oben.
  ) else (
    echo The server ended with an error. The message is shown above.
  )
  pause
)

endlocal
