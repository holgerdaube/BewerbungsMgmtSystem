@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
rem Bewerbungs-Management-System unter Windows beenden (Doppelklick oder: stop_windows.bat [--force]).
rem Windows-Pendant zu stop.command (macOS): gleiches Verhalten, nur mit den unter Windows
rem ueblichen Bordmitteln (netstat/taskkill statt lsof/kill).
rem
rem Warum nicht einfach taskkill? Weil ein Stopp im falschen Moment Arbeit vernichtet: Der Server
rem startet Skill-Laeufe als Kindprozesse, und die Beirats-Debatten laufen IM Server selbst
rem (tasks\lessons.md, "Server-Neustart toetet In-Server-Laeufe") -- ein hartes Beenden laesst
rem eine bereits bezahlte Debatte unwiederbringlich sterben. Deshalb wird zuerst geprueft, ob
rem gerade etwas laeuft, und nachgefragt.
rem
rem Setup/Details: docs\SETUP-WINDOWS.md.

set "PORT=8000"
if not "%PORT_OVERRIDE%"=="" set "PORT=%PORT_OVERRIDE%"

set "FORCE=0"
if /i "%~1"=="--force" set "FORCE=1"

rem ── Lauschenden Prozess finden ──────────────────────────────────────────────────────────
rem "netstat -ano" listet auch Verbindungen im Zustand TIME_WAIT o. ae. -- nur LISTENING zaehlt,
rem sonst wuerde eine gerade geschlossene Browser-Verbindung als "laeuft noch" gelten.
set "SERVERPID="
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /r /c:"TCP.*:%PORT% .*LISTENING"') do (
  if not defined SERVERPID set "SERVERPID=%%P"
)

if not defined SERVERPID (
  echo Auf Port %PORT% laeuft nichts -- das Bewerbungs-Management ist bereits beendet.
  timeout /t 3 >nul
  exit /b 0
)

echo Bewerbungs-Management laeuft auf Port %PORT% ^(Prozess: %SERVERPID%^)

rem ── Laufende Agent-Laeufe erkennen ──────────────────────────────────────────────────────
rem PowerShell statt curl+findstr: Die API antwortet als EINE JSON-Zeile, findstr zaehlt aber
rem Zeilen, nicht Vorkommen -- es haette immer "1" gemeldet, egal wie viele Laeufe aktiv sind.
rem Invoke-RestMethod parst das JSON und .Count liefert die echte Anzahl. Antwortet der Server
rem nicht (haengt/faehrt schon herunter), bleibt die Anzahl unbekannt und wir beenden ohne
rem Rueckfrage -- besser als ein Stop-Skript, das dann gar nicht mehr stoppen kann.
rem -Command ist NICHT von der PowerShell-Ausfuehrungsrichtlinie betroffen (die gilt nur fuer
rem .ps1-Dateien) -- gleiche Ueberlegung wie im Browser-Aufruf von start_windows.bat.
rem Gezaehlt werden BEIDE Zustaende: "running" ist der Lauf, der gerade stirbt -- "queued" sind
rem die Schritte einer Kette, die danach nie mehr an die Reihe kaemen (ein Tageslauf hat sieben
rem davon, waehrend Schritt eins laeuft).
set "ANZAHL=?"
for /f %%C in ('powershell -NoProfile -Command "try { $u='http://127.0.0.1:%PORT%/api/tasks?status='; @((Invoke-RestMethod -Uri ($u+'running^&limit=50') -TimeoutSec 3)).Count + @((Invoke-RestMethod -Uri ($u+'queued^&limit=50') -TimeoutSec 3)).Count } catch { '?' }" 2^>nul') do set "ANZAHL=%%C"

if not "%ANZAHL%"=="?" if not "%ANZAHL%"=="0" (
  echo.
  echo   ACHTUNG: Es laufen gerade %ANZAHL% Agent-Lauf/Laeufe.
  echo   Beenden bricht sie ab. Skill-Laeufe lassen sich spaeter neu starten,
  echo   eine laufende Beirats-Debatte ist verloren -- sie laeuft im Server selbst.
  echo.
  if "%FORCE%"=="1" (
    echo   --force gesetzt: wird trotzdem beendet.
  ) else (
    set /p "WEITER=  Trotzdem beenden? [j/N] "
    if /i not "!WEITER!"=="j" (
      echo Abgebrochen -- nichts veraendert.
      timeout /t 3 >nul
      exit /b 1
    )
  )
)

rem ── Freundlich beenden ──────────────────────────────────────────────────────────────────
rem /T nimmt die Kindprozesse mit (headless gestartete Skill-Laeufe haengen als Kinder am
rem Server); ohne /T blieben sie als Waisen zurueck und wuerden weiter Kosten verursachen.
echo Beende...
taskkill /PID %SERVERPID% /T >nul 2>&1

rem Bis zu 10 s auf den sauberen Abgang warten.
set "WARTEN=0"
:warteschleife
timeout /t 1 >nul
set "NOCHDA="
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /r /c:"TCP.*:%PORT% .*LISTENING"') do set "NOCHDA=%%P"
if not defined NOCHDA goto beendet
set /a WARTEN+=1
if %WARTEN% lss 10 goto warteschleife

rem ── Notfalls hart ───────────────────────────────────────────────────────────────────────
echo Prozess reagiert nicht auf das normale Beenden -- erzwinge das Ende.
taskkill /F /PID %SERVERPID% /T >nul 2>&1
timeout /t 2 >nul

set "NOCHDA="
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /r /c:"TCP.*:%PORT% .*LISTENING"') do set "NOCHDA=%%P"
if defined NOCHDA (
  echo FEHLER: Port %PORT% ist weiterhin belegt ^(Prozess %NOCHDA%^).
  echo Pruefen mit: netstat -ano ^| findstr :%PORT%
  pause
  exit /b 1
)

:beendet
echo.
echo Bewerbungs-Management beendet. Neu starten: start_windows.bat
timeout /t 3 >nul
endlocal
