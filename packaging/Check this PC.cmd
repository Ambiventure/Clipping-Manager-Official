@echo off
rem Runs the application's own self check and holds the window open.
rem
rem Double-clicking the .exe with --selftest is not possible from Explorer, and
rem running it from a Command Prompt means typing a long path. This is the same
rem check, one double-click, in a window that stays put long enough to read.

setlocal
cd /d "%~dp0"
set REPORT=%TEMP%\clippings-manager-selfcheck.txt

echo.
echo  Checking this computer. One moment...
echo.

"%~dp0Clippings Manager.exe" --selftest
set RESULT=%ERRORLEVEL%

rem The check writes its report to a file as well as printing it. Showing the
rem file is what makes this reliable: a windowed program has to borrow the
rem console it was started from, and a locked-down machine can refuse that. The
rem file is always there.
if exist "%REPORT%" (
    echo.
    echo  ================= REPORT =================
    type "%REPORT%"
    echo  ==========================================
)

echo.
if "%RESULT%"=="0" (
    echo  ---------------------------------------------------------------
    echo   This computer is ready. Close this window and start the app.
    echo  ---------------------------------------------------------------
) else (
    echo  ---------------------------------------------------------------
    echo   Something above did not pass. The failing line says which.
    echo   "BEFORE YOU START - setting up a new PC.txt" explains each one.
    echo.
    echo   To send this on, attach:
    echo     %REPORT%
    echo  ---------------------------------------------------------------
)

echo.
echo  Press any key to close.
pause >nul
endlocal
