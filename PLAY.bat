@echo off
rem PLAY.bat - starts Fire Emblem Fates (Special Edition, USA) straight into the game:
rem the standalone program play\game\Fire Emblem Fates.exe when it is built, else Zakuro.
rem Start here: Read Me First.txt. The work is done by tools\play\play.py.
rem   PLAY.bat --dry-run   checks everything and prints the command, starts nothing
rem   PLAY.bat --setup     the Getting ready window (find your game file, the Randomizer);
rem                        it also opens by itself when something is missing or wrong
rem   PLAY.bat --help      every option
setlocal
set "HERE=%~dp0"
set "FEF_LAUNCHER=1"
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY goto nopython

%PY% "%HERE%tools\play\play.py" %*
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" goto failed
endlocal
exit /b 0

:failed
echo.
if %RC% LSS 0 echo Python stopped with a Windows error (code %RC%). If this happens every time, reinstall Python 3 from python.org.
echo The game was not started. The lines above say why and what to do.
if not defined PLAY_NO_PAUSE pause
endlocal
exit /b 1

:nopython
echo Python 3 was not found. PLAY needs it (python.org, or "python" from the Microsoft Store).
echo Zakuro itself still works without it: open zakuro.exe in your Zakuro folder.
if not defined PLAY_NO_PAUSE pause
endlocal
exit /b 1
