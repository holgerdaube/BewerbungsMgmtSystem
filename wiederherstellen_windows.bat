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
rem Sicherung der Datenbank zurueckspielen (Doppelklick oder: wiederherstellen_windows.bat [Optionen]).
rem Das BMS muss vorher beendet sein (stop_windows.bat). Windows-Pendant zu wiederherstellen.command
rem (macOS): reicht den Programmordner an scripts\bms_wiederherstellen.py durch (P2-66).
rem
rem ALLES in EINEM geklammerten Block, der mit "exit /b" endet: cmd.exe liest eine Batch-Datei
rem waehrend der Ausfuehrung zeilenweise nach, ein Update kann aber genau DIESE Datei ersetzen.
rem Ein Block in runden Klammern wird als Ganzes eingelesen (gleiches Muster wie update_windows.bat).
rem Variablen, die im Block gesetzt werden, mit "!VAR!" lesen (enabledelayedexpansion).
rem "%~dp0." statt "%~dp0": ein Backslash vor dem schliessenden Anfuehrungszeichen zerlegt das
rem Argument in cmd.exe.
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
  "!VENV!" scripts\bms_wiederherstellen.py --installation "%~dp0." %*
  set "ERGEBNIS=!ERRORLEVEL!"
  echo.
  pause
  exit /b !ERGEBNIS!
)
