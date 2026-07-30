@echo off
REM ==========================================================================
REM  Merged Chat relay - one-time setup
REM
REM  Installs the Python packages relay.py needs and creates app.properties
REM  from the template if it doesn't exist yet. Safe to run more than once.
REM ==========================================================================

setlocal
cd /d "%~dp0"

echo.
echo  Merged Chat relay - installing requirements
echo  ==========================================
echo.

REM --- find Python ---------------------------------------------------------
REM "py" (the Windows launcher) is preferred: it works even when python.exe
REM isn't on PATH, which is the usual state after a default install.
set "PY="
where py >nul 2>&1 && set "PY=py"
if not defined PY (
    where python >nul 2>&1 && set "PY=python"
)

if not defined PY (
    echo  [X] Python was not found.
    echo.
    echo      Install it from https://www.python.org/downloads/
    echo      and TICK "Add python.exe to PATH" during setup.
    echo.
    pause
    exit /b 1
)

for /f "tokens=*" %%v in ('%PY% --version 2^>^&1') do set "PYVER=%%v"
echo  [OK] Found %PYVER%  (using "%PY%")
echo.

REM --- install packages ----------------------------------------------------
REM No --upgrade: only install what's missing. Silently bumping a package that
REM already works is a good way to break someone's setup an hour before stream.
echo  Installing packages from requirements.txt ...
echo.
%PY% -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo  [X] pip failed.
    echo.
    echo      If it says pip is missing, run:  %PY% -m ensurepip --upgrade
    echo      If it's a permissions error, try: %PY% -m pip install --user -r requirements.txt
    echo.
    pause
    exit /b 1
)

echo.
%PY% -c "import websockets; print('  [OK] websockets ' + websockets.__version__ + ' ready')"
if errorlevel 1 (
    echo  [X] websockets still won't import - the install did not take effect.
    pause
    exit /b 1
)

REM --- config file ---------------------------------------------------------
echo.
if exist "app.properties" (
    echo  [OK] app.properties already exists - leaving it alone.
) else (
    if not exist "app.properties.example" (
        echo  [X] app.properties.example is missing from this folder.
        pause
        exit /b 1
    )
    copy /y "app.properties.example" "app.properties" >nul
    echo  [OK] Created app.properties from the template.
    echo.
    echo      EDIT IT NOW - it needs your channel name, YouTube video ID and
    echo      API key before the relay can do anything useful.
    echo.
    choice /c YN /n /m "      Open it in Notepad? [Y/N] "
    if not errorlevel 2 start "" notepad "app.properties"
)

echo.
echo  ==========================================
echo   Setup complete. Start the relay with:
echo.
echo       start-relay.bat
echo.
echo  ==========================================
echo.
pause
endlocal
