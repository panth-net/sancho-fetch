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
  echo   ... Installing the Python package manager (uv)...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 ^| iex"
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

echo   ... Installing Sancho...
set "INSTALL_LOG=%TEMP%\sancho_uv_install_%RANDOM%%RANDOM%.log"
uv tool install . > "%INSTALL_LOG%" 2>&1
if errorlevel 1 (
  findstr /i /c:"already installed" /c:"already exists" "%INSTALL_LOG%" >NUL
  if errorlevel 1 (
    type "%INSTALL_LOG%"
    del "%INSTALL_LOG%" >NUL 2>&1
    goto :install_failed
  )
  type "%INSTALL_LOG%"
  del "%INSTALL_LOG%" >NUL 2>&1
  echo   ... Existing Sancho install found. Refreshing it from this folder...
  uv tool uninstall sancho-fetch >NUL 2>&1
  uv tool install .
  if errorlevel 1 goto :install_failed
) else (
  del "%INSTALL_LOG%" >NUL 2>&1
)
for /f "delims=" %%d in ('uv tool dir --bin 2^>NUL') do set "UV_TOOL_BIN=%%d"
if defined UV_TOOL_BIN set "PATH=%UV_TOOL_BIN%;%USERPROFILE%\.local\bin;%PATH%"
set "SANCHO_CMD=sancho"
if defined UV_TOOL_BIN if exist "%UV_TOOL_BIN%\sancho.exe" set "SANCHO_CMD=%UV_TOOL_BIN%\sancho.exe"
echo   OK  Sancho installed

echo   ... Creating your workspace and registering it...
"%SANCHO_CMD%" setup --path "%REPO_ROOT%" --install-claude-desktop
if errorlevel 1 goto :setup_failed

echo.
echo Installer finished.
echo.
echo What's next:
echo.
echo   1. Open Claude Code / Codex / Cursor / VS Code pointed at this folder,
echo      and just describe the data you want. The AI runs Sancho for you.
echo      ChatGPT web needs the hosted/remote connector path, not a local folder.
echo      If setup said Claude Desktop config was installed, fully restart Claude Desktop.
echo      If setup said it could not install Claude Desktop automatically, use:
echo        sancho mcp config --client claude-desktop --workspace "%REPO_ROOT%" --install
echo      or the generated snippet under sancho-workspace\mcp\.
echo.
echo   2. Your API keys live in:
echo        %REPO_ROOT%\sancho-workspace\.env
echo      This file is HIDDEN by default.
echo      - On Windows: in File Explorer, View ^-^> Show ^-^> Hidden items.
echo      - Or just ask your AI to open it for you.
echo.
echo   3. You do NOT need to be a coder. The AI speaks in plain English
echo      unless you change SANCHO_DEVELOPER_MODE=true inside .env.
echo.
popd
endlocal
exit /b 0

:uv_install_failed
echo ERROR: uv install failed. Check your internet connection and try again.
popd
endlocal
exit /b 1

:install_failed
echo ERROR: uv tool install failed. Sancho needs Python 3.11 or newer; uv normally downloads a compatible Python automatically.
popd
endlocal
exit /b 1

:setup_failed
echo ERROR: sancho setup failed.
popd
endlocal
exit /b 1

:end_fail
popd
endlocal
exit /b 1
