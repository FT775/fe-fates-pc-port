@echo off
rem RELEASE.bat - for the project owner: the one-command release, NO engine build (docs/RELEASE.md).
rem Players do not need it: to play, use PLAY.bat.
rem It checks, runs the core tests and the smoke, packs the zip, writes the record and a LOCAL tag.
rem It never pushes. The work is done by tools\release\release.py.
rem   RELEASE.bat               the release (asks you to press Enter first)
rem   RELEASE.bat --dry-run     shows what would run and how long; changes nothing
rem   RELEASE.bat status        where things stand; changes nothing
rem   RELEASE.bat undo r68      puts back what release r68 changed (asks you to type r68)
rem   RELEASE.bat push r68      sends r68 to the private GitHub repo: only you run this (asks you to type r68)
rem   RELEASE.bat publish r86   makes and checks the public one-commit copy of r86; sends nothing, prints the commands
setlocal
echo This button is for the project owner: it makes a release of the project. To play, use PLAY.bat.
set "HERE=%~dp0"
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY goto nopython

%PY% "%HERE%tools\release\release.py" %*
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" (echo Finished. The lines above say what was done.) else (echo Stopped. The lines above say why and what to do.)
if not defined RELEASE_NO_PAUSE pause
endlocal & exit /b %RC%

:nopython
echo Python 3 was not found. The release needs it (python.org, or "python" from the Microsoft Store).
if not defined RELEASE_NO_PAUSE pause
endlocal
exit /b 1
