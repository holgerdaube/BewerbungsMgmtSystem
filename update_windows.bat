@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
rem Terminal-Sprache (P2-95): BMS_TERMINAL_SPRACHE (de/en) gewinnt, sonst die Windows-Anzeigesprache.
rem Beginnt der Wert mit "de", gilt Deutsch, sonst Englisch (auch bei jedem Fehler). Die Variable
rem bleibt gesetzt, damit die Python-Werkzeuge dieselbe Sprache nehmen. Von der Wahl haengt keine
rem Meldung und kein Ablauf ab: Schlaegt die Erkennung fehl, gilt Englisch.
if not defined BMS_TERMINAL_SPRACHE for /f %%L in ('powershell -NoProfile -Command "(Get-UICulture).TwoLetterISOLanguageName" 2^>nul') do set "BMS_TERMINAL_SPRACHE=%%L"
if not defined BMS_TERMINAL_SPRACHE set "BMS_TERMINAL_SPRACHE=en"
if /i "%BMS_TERMINAL_SPRACHE:~0,2%"=="de" (set "BMS_TERMINAL_SPRACHE=de") else (set "BMS_TERMINAL_SPRACHE=en")
rem Bewerbungs-Management-System aktualisieren (Doppelklick oder: update_windows.bat [Optionen]).
rem Windows-Pendant zu update.command (macOS): reicht den Programmordner an
rem scripts\bms_update.py durch (P2-51), das die eigentliche Arbeit macht.
rem
rem ALLES in EINEM geklammerten Block, der mit "exit /b" endet: cmd.exe liest eine Batch-Datei
rem waehrend der Ausfuehrung zeilenweise nach, sobald es die naechste Zeile braucht. Ein Update
rem ersetzt aber genau DIESE Datei. Ein Block in runden Klammern wird von cmd.exe als Ganzes
rem eingelesen, bevor die erste Zeile darin laeuft -- das Risiko entfaellt (gleiches Muster wie
rem in stop_windows.bat mit dem Beenden-Ablauf).
rem
rem "enabledelayedexpansion" + "!VAR!" statt "%VAR%" fuer JEDE Variable, die INNERHALB dieses
rem Blocks per "set" gesetzt wird (VENV, ERGEBNIS): cmd.exe ersetzt "%VAR%" beim EINLESEN des
rem GANZEN Blocks (also VOR der ersten Zeile darin), ein "set" weiter unten im selben Block kaeme
rem fuer eine spaetere "%VAR%"-Stelle immer zu spaet (empirisch mit "%ERRORLEVEL%" geprueft: ohne
rem "!ERRORLEVEL!" haette ERGEBNIS den Stand VOR dem Python-Aufruf eingefangen, nie den echten
rem Exit-Code). "%~dp0" und "%USERPROFILE%" bleiben bewusst bei "%...%": beides steht schon fest,
rem bevor der Block beginnt, und aendert sich waehrend des Laufs nicht.
rem
rem Setup/Details: docs\SETUP-WINDOWS.md.
rem
rem "%~dp0." statt "%~dp0": %~dp0 endet immer mit einem Backslash, und ein Backslash direkt vor
rem dem schliessenden Anfuehrungszeichen zerlegt das Argument in cmd.exe (die folgenden Zeichen
rem wuerden zum Anfuehrungszeichen gehoeren statt es zu beenden). Der Punkt macht daraus einen
rem gewoehnlichen, unproblematischen Pfad (z. B. "C:\BMS\.").
rem
(
  cd /d "%~dp0."
  set "VENV=%USERPROFILE%\.bewerbung_mgmt_venv\Scripts\python.exe"
  if not exist "!VENV!" (
    if "%BMS_TERMINAL_SPRACHE%"=="de" (
      echo Fehler: Die Python-Umgebung wurde nicht gefunden unter %USERPROFILE%\.bewerbung_mgmt_venv
      echo Bitte zuerst die Einrichtung aus BMS_Install_Windows.md abschliessen.
    ) else (
      echo Error: The Python environment was not found at %USERPROFILE%\.bewerbung_mgmt_venv
      echo Please complete the setup from BMS_Install_Windows.en.md first.
    )
    pause
    exit /b 1
  )
  "!VENV!" scripts\bms_update.py --installation "%~dp0." %*
  set "ERGEBNIS=!ERRORLEVEL!"
  echo.
  pause
  exit /b !ERGEBNIS!
)
