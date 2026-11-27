@echo off
rem PLAY RANDOMIZED.bat - new or continued RANDOMIZED games of Fire Emblem Fates (F-041 #4).
rem Each randomized game is its own profile in play\randomizer\<seed>\ with its own saves and its own mods.
rem Your normal PLAY.bat, normal save and normal mods are not used or changed. Steps: docs\RANDOMIZER_PAGE.md.
rem The work is done by tools\play\rando.py (it uses PLAY's own checks and program).
rem   PLAY RANDOMIZED.bat              a small menu: New randomized game / Continue randomized game / List
rem   PLAY RANDOMIZED.bat --dry-run    the same, but starts nothing
rem   PLAY RANDOMIZED.bat --check      only the checks (the game file in roms, the program); makes nothing
rem   PLAY RANDOMIZED.bat --help       every option
setlocal
set "HERE=%~dp0"
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY goto nopython

%PY% "%HERE%tools\play\rando.py" %*
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" goto failed
if not defined PLAY_NO_PAUSE pause
endlocal
exit /b 0

:failed
echo.
if %RC% LSS 0 echo Python stopped with a Windows error (code %RC%). If this happens every time, reinstall Python 3 from python.org.
echo The randomized game was not started. The lines above say why and what to do.
if not defined PLAY_NO_PAUSE pause
endlocal
exit /b 1

:nopython
echo Python 3 was not found. PLAY RANDOMIZED needs it (python.org, or "python" from the Microsoft Store).
if not defined PLAY_NO_PAUSE pause
endlocal
exit /b 1
