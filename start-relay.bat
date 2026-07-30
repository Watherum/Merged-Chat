@echo off
REM ==========================================================================
REM  Merged Chat relay - start
REM
REM  Leave this window open while you stream; closing it stops the relay and
REM  every open view falls back to connecting on its own.
REM
REM  If the configured port is busy, relay.py moves up to the next free one
REM  and the overlay scans that range, so nothing needs reconfiguring.
REM
REM  Optional: pass a different properties file to run a second setup, e.g.
REM      start-relay.bat other-channel.properties
REM ==========================================================================

setlocal
cd /d "%~dp0"

title Merged Chat relay

REM The relay logs channel names, emotes and status text that may not be ASCII.
REM Without these two lines cmd renders them as mojibake.
chcp 65001 >nul 2>&1
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"

REM --- find Python ---------------------------------------------------------
set "PY="
where py >nul 2>&1 && set "PY=py"
if not defined PY (
    where python >nul 2>&1 && set "PY=python"
)

if not defined PY (
    echo.
    echo  [X] Python was not found. Run install-requirements.bat first.
    echo.
    pause
    exit /b 1
)

REM --- check the dependency ------------------------------------------------
%PY% -c "import websockets" >nul 2>&1
if errorlevel 1 (
    echo.
    echo  [X] The 'websockets' package is not installed.
    echo.
    echo      Run install-requirements.bat, or install it directly:
    echo          %PY% -m pip install websockets
    echo.
    pause
    exit /b 1
)

REM --- check the config ----------------------------------------------------
set "PROPS=%~1"
if "%PROPS%"=="" set "PROPS=app.properties"

if not exist "%PROPS%" (
    echo.
    echo  [X] %PROPS% not found.
    echo.
    echo      Run install-requirements.bat to create it from the template,
    echo      or copy it yourself:
    echo          copy app.properties.example app.properties
    echo.
    pause
    exit /b 1
)

REM --- go ------------------------------------------------------------------
echo.
echo  Starting the Merged Chat relay ^(config: %PROPS%^)
echo  Close this window to stop it.
echo.

%PY% relay.py "%PROPS%"
set "RC=%ERRORLEVEL%"

REM Exit code 0 is a clean Ctrl+C shutdown; anything else is worth reading, so
REM hold the window open instead of letting it vanish with the error on it.
echo.
if not "%RC%"=="0" (
    echo  ==========================================
    echo   The relay stopped with an error ^(code %RC%^).
    echo   The message above says why.
    echo  ==========================================
) else (
    echo  Relay stopped.
)
echo.
pause
endlocal
