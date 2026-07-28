@echo off
REM Double-click installer for Windows. Wraps setup.bat so non-coders can
REM install Sancho Fetch from Explorer.
pushd "%~dp0"
if errorlevel 1 (
  echo Could not open the installer folder.
  echo Press any key to close this window.
  pause >NUL
  exit /b 1
)
call setup.bat
set EXITCODE=%ERRORLEVEL%
echo.
echo Press any key to close this window.
pause >NUL
popd
exit /b %EXITCODE%
