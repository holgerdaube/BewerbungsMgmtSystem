@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
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
    echo Fehler: Die Python-Umgebung wurde nicht gefunden unter %USERPROFILE%\.bewerbung_mgmt_venv
    echo Bitte zuerst die Einrichtung aus BMS_Install_Windows.md abschliessen.
    pause
    exit /b 1
  )
  "!VENV!" scripts\bms_wiederherstellen.py --installation "%~dp0." %*
  set "ERGEBNIS=!ERRORLEVEL!"
  echo.
  pause
  exit /b !ERGEBNIS!
)
