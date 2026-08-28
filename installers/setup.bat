@echo off
REM Sancho Fetch installer for Windows.
REM Bootstraps uv, lets uv provide a compatible Python, installs Sancho, and runs
REM `sancho setup` in the repo folder.

setlocal enableextensions
set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "REPO_ROOT=%%~fI"
pushd "%REPO_ROOT%"

echo Sancho Fetch installer
echo ======================
echo.
echo Setting up your Sancho Fetch library at:
echo   "%REPO_ROOT%"
echo.

if not exist "%REPO_ROOT%\pyproject.toml" (
  echo   X  This installer must run from an extracted sancho-fetch folder.
  echo      If you downloaded a ZIP, unzip it first, then double-click this installer again.
  goto :end_fail
)

where uv >NUL 2>&1
if errorlevel 1 (
  echo   ... Installing the Python package manager ^(uv^)...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
  if errorlevel 1 goto :uv_install_failed
  set "PATH=%USERPROFILE%\.local\bin;%PATH%"
)
where uv >NUL 2>&1
if errorlevel 1 (
  echo   X  uv was installed but is not available in this window yet.
  echo      Close this installer window, open it again, and retry.
  goto :end_fail
)
echo   OK  Package manager (uv) ready

echo   ... Building and validating Sancho before replacing the installed tool...
set "BUILD_DIR=%TEMP%\sancho_build_%RANDOM%%RANDOM%"
mkdir "%BUILD_DIR%"
if errorlevel 1 goto :build_failed
uv build --wheel --out-dir "%BUILD_DIR%" .
if errorlevel 1 goto :build_failed
set "WHEEL_PATH="
for %%W in ("%BUILD_DIR%\sancho_fetch-*.whl") do set "WHEEL_PATH=%%~fW"
if not defined WHEEL_PATH goto :build_failed

echo   ... Installing the validated wheel...
set "INSTALL_LOG=%TEMP%\sancho_uv_install_%RANDOM%%RANDOM%.log"
uv tool install --reinstall "%WHEEL_PATH%" > "%INSTALL_LOG%" 2>&1
if errorlevel 1 (
  type "%INSTALL_LOG%"
  del "%INSTALL_LOG%" >NUL 2>&1
  goto :install_failed
) else (
  del "%INSTALL_LOG%" >NUL 2>&1
)
for /f "delims=" %%d in ('uv tool dir --bin 2^>NUL') do set "UV_TOOL_BIN=%%d"
if defined UV_TOOL_BIN set "PATH=%UV_TOOL_BIN%;%USERPROFILE%\.local\bin;%PATH%"
set "SANCHO_CMD=sancho"
if defined UV_TOOL_BIN if exist "%UV_TOOL_BIN%\sancho.exe" set "SANCHO_CMD=%UV_TOOL_BIN%\sancho.exe"
echo   OK  Sancho installed

echo   ... Creating your workspace and registering it...
"%SANCHO_CMD%" setup --path "%REPO_ROOT%" --switch-workspace
if errorlevel 1 goto :setup_failed

echo.
echo Installer finished.
echo.
echo What's next:
echo.
echo   1. Sancho is installed computer-wide. You do not need to open this folder again.
echo      In Claude Desktop, use the Code tab. In Codex, start a Code chat.
echo      Regular chats cannot access your local Sancho installation.
echo      ChatGPT web needs the hosted/remote connector path, not a local folder.
echo      Setup configures detected supported clients and reports restart or policy actions.
echo      It never installs the desktop clients themselves.
echo.
echo   2. Your API keys live in:
echo        %REPO_ROOT%\sancho-workspace\.env
echo      This file is HIDDEN by default.
echo      If it is missing, run sancho env open to create it from .env.example.
echo      - On Windows: in File Explorer, View ^-^> Show ^-^> Hidden items.
echo      - Or just ask your AI to open it for you.
echo.
echo   3. You do NOT need to be a coder. The AI speaks in plain English
echo      unless you change SANCHO_DEVELOPER_MODE=true inside .env.
echo.
if defined BUILD_DIR rmdir /s /q "%BUILD_DIR%" >NUL 2>&1
popd
endlocal
exit /b 0

:uv_install_failed
echo ERROR: uv install failed. Check your internet connection and try again.
popd
endlocal
exit /b 1

:install_failed
echo ERROR: uv could not install the validated wheel. The installer did not uninstall another tool.
if defined BUILD_DIR rmdir /s /q "%BUILD_DIR%" >NUL 2>&1
popd
endlocal
exit /b 1

:build_failed
echo ERROR: Sancho could not be built. The previously installed command was not changed.
if defined BUILD_DIR rmdir /s /q "%BUILD_DIR%" >NUL 2>&1
popd
endlocal
exit /b 1

:setup_failed
echo ERROR: sancho setup failed.
if defined BUILD_DIR rmdir /s /q "%BUILD_DIR%" >NUL 2>&1
popd
endlocal
exit /b 1

:end_fail
popd
endlocal
exit /b 1
