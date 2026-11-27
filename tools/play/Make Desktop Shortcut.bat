@echo off
rem Puts a "PLAY Fire Emblem Fates" shortcut on your Desktop that starts PLAY.bat.
rem Nothing is made until you run this. Add --force to replace an existing one,
rem or --dry-run to see what it would make.
setlocal
set "HERE=%~dp0"
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY goto nopython

%PY% "%HERE%play.py" --make-shortcut %*
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" goto failed
if not defined PLAY_NO_PAUSE pause
endlocal
exit /b 0

:failed
if %RC% LSS 0 echo Python stopped with a Windows error (code %RC%). If this happens every time, reinstall Python 3 from python.org.
if not defined PLAY_NO_PAUSE pause
endlocal
exit /b 1

:nopython
echo Python 3 was not found. Install it, or make the shortcut by hand:
echo right-click PLAY.bat, Send to, Desktop (create shortcut).
if not defined PLAY_NO_PAUSE pause
endlocal
exit /b 1
