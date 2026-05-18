@echo off
REM Double-click uninstaller for Windows. Wraps uninstall.bat so non-coders
REM can uninstall Sancho Fetch from Explorer.
pushd "%~dp0"
if errorlevel 1 (
  echo Could not open the uninstaller folder.
  echo Press any key to close this window.
  pause >NUL
  exit /b 1
)
call uninstall.bat
set EXITCODE=%ERRORLEVEL%
echo.
echo Press any key to close this window.
pause >NUL
popd
exit /b %EXITCODE%
