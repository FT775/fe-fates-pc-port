@echo off
rem RELEASE WITH ENGINE BUILD.bat - for the project owner: the release WITH an engine build (docs/RELEASE.md).
rem Players do not need it: to play, use PLAY.bat.
rem The first screen lists every build it will run; pressing Enter there is your OK for exactly those builds.
rem The build goes to a staging folder first; the old files are backed up before anything is installed,
rem and any failed check puts them back. It never pushes. The work is done by tools\release\release.py.
rem   "RELEASE WITH ENGINE BUILD.bat" --dry-run    shows the builds and times; changes nothing
setlocal
echo This button is for the project owner: it makes a release of the project. To play, use PLAY.bat.
set "HERE=%~dp0"
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY goto nopython

%PY% "%HERE%tools\release\release.py" --engine %*
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
