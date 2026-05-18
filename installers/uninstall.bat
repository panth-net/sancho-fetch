@echo off
REM Sancho Fetch uninstaller for Windows.
REM
REM Removes everything installers\setup.bat installs:
REM   - the `sancho` CLI (via `uv tool uninstall sancho-fetch`)
REM   - the library pointer at %USERPROFILE%\.sancho\
REM   - AI skills at %USERPROFILE%\.claude\skills\sancho{,-update}\ and %USERPROFILE%\.agents\skills\sancho{,-update}\
REM   - the `sancho` MCP server entry from Claude Desktop's config (other entries preserved)
REM
REM By default your sancho-workspace\ folder (the visible folder with your .env,
REM fetched-data, custom modules, playbooks, outputs, logs) is KEPT.
REM Pass --purge to also delete sancho-workspace\.
REM
REM Flags:
REM   --purge   Also delete sancho-workspace\ (your fetched data and .env)
REM   --yes     Skip the interactive "are you sure?" prompts
REM   --help    Show this message and exit

setlocal enableextensions enabledelayedexpansion
set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "REPO_ROOT=%%~fI"
set "WORKSPACE_DIR=%REPO_ROOT%\sancho-workspace"

set "PURGE=0"
set "ASSUME_YES=0"
:parse_args
if "%~1"=="" goto :after_args
if /i "%~1"=="--purge" set "PURGE=1" & shift & goto :parse_args
if /i "%~1"=="--yes" set "ASSUME_YES=1" & shift & goto :parse_args
if /i "%~1"=="-y" set "ASSUME_YES=1" & shift & goto :parse_args
if /i "%~1"=="--help" goto :show_help
if /i "%~1"=="-h" goto :show_help
echo Unknown flag: %~1
echo Run "installers\uninstall.bat --help" for usage.
endlocal
exit /b 2
:after_args

echo Sancho Fetch uninstaller
echo ========================
echo.
echo This will remove the sancho CLI, library pointer, AI skills, and the
echo Claude Desktop MCP entry from this computer.
echo.
if "%PURGE%"=="1" (
  echo   --purge: will ALSO delete your sancho-workspace folder:
  echo     %WORKSPACE_DIR%
  echo   This contains your .env ^(API keys^), fetched-data, custom modules,
  echo   playbooks, outputs, and logs. THIS IS DESTRUCTIVE.
) else (
  echo   Your sancho-workspace folder will be KEPT:
  echo     %WORKSPACE_DIR%
  echo   ^(Pass --purge to delete it too.^)
)
echo.

if "%ASSUME_YES%"=="0" (
  set /p "ANSWER=Proceed? [y/N] "
  if /i not "!ANSWER!"=="y" if /i not "!ANSWER!"=="yes" (
    echo Aborted.
    endlocal
    exit /b 0
  )
)

REM 1. Uninstall the CLI via uv. Skip silently if uv or the tool is missing.
where uv >NUL 2>&1
if errorlevel 1 (
  echo   --  uv not found; nothing to uninstall via uv
) else (
  uv tool list 2>NUL | findstr /b /c:"sancho-fetch" >NUL
  if errorlevel 1 (
    echo   --  sancho CLI not installed via uv
  ) else (
    uv tool uninstall sancho-fetch >NUL 2>&1
    if errorlevel 1 (
      echo   !!  uv tool uninstall sancho-fetch failed; remove it manually with that command
    ) else (
      echo   OK  Removed sancho CLI ^(uv tool uninstall sancho-fetch^)
    )
  )
)

REM 2. Remove the library pointer and the quick MCP workspace.
set "SANCHO_HOME=%USERPROFILE%\.sancho"
if exist "%SANCHO_HOME%" (
  rmdir /s /q "%SANCHO_HOME%"
  echo   OK  Removed library pointer ^(%SANCHO_HOME%^)
) else (
  echo   --  Library pointer not found ^(%SANCHO_HOME%^)
)

REM 3. Remove AI assistant skills from the two skill dirs.
set "REMOVED_ANY_SKILL=0"
for %%B in ("%USERPROFILE%\.claude\skills" "%USERPROFILE%\.agents\skills") do (
  for %%N in (sancho sancho-update) do (
    set "TARGET=%%~B\%%N"
    if exist "!TARGET!" (
      rmdir /s /q "!TARGET!"
      echo   OK  Removed AI skill ^(!TARGET!^)
      set "REMOVED_ANY_SKILL=1"
    )
  )
)
if "%REMOVED_ANY_SKILL%"=="0" (
  echo   --  No AI skills found under %USERPROFILE%\.claude\skills or %USERPROFILE%\.agents\skills
)

REM 4. Surgically remove the `sancho` entry from Claude Desktop's MCP config.
set "CLAUDE_CFG=%APPDATA%\Claude\claude_desktop_config.json"
if exist "%CLAUDE_CFG%" (
  where python >NUL 2>&1
  if errorlevel 1 (
    where py >NUL 2>&1
    if errorlevel 1 (
      echo   !!  Python not found; remove the 'sancho' entry from %CLAUDE_CFG% manually
    ) else (
      call :strip_claude_entry py "%CLAUDE_CFG%"
    )
  ) else (
    call :strip_claude_entry python "%CLAUDE_CFG%"
  )
) else (
  echo   --  No Claude Desktop config edits made
)

REM 5. Optionally remove the workspace.
if "%PURGE%"=="1" (
  if exist "%WORKSPACE_DIR%" (
    rmdir /s /q "%WORKSPACE_DIR%"
    echo   OK  Removed workspace ^(%WORKSPACE_DIR%^)
  ) else (
    echo   --  Workspace not found ^(%WORKSPACE_DIR%^)
  )
) else (
  if exist "%WORKSPACE_DIR%" (
    echo   --  Kept workspace ^(%WORKSPACE_DIR%^)
    echo       Delete it yourself if you also want to remove your .env and fetched data,
    echo       or re-run with: installers\uninstall.bat --purge
  )
)

echo.
echo Uninstall finished.
echo.
echo If Claude Desktop is open, fully quit and reopen it so the MCP entry change takes effect.
endlocal
exit /b 0

:strip_claude_entry
REM %1 = python interpreter, %2 = config path
%~1 -c "import json,sys,pathlib; p=pathlib.Path(sys.argv[1]); d=json.loads(p.read_text(encoding='utf-8')); s=d.get('mcpServers') if isinstance(d,dict) else None; sys.exit(1) if not isinstance(s,dict) or 'sancho' not in s else (s.pop('sancho'), p.write_text(json.dumps(d,indent=2)+'\n',encoding='utf-8'), sys.exit(0))" %2
if errorlevel 2 (
  echo   !!  Could not edit %~2 ^(parse error^); remove the sancho entry manually
) else if errorlevel 1 (
  echo   --  No 'sancho' entry in %~2
) else (
  echo   OK  Removed 'sancho' entry from %~2
)
goto :eof

:show_help
echo Sancho Fetch uninstaller for Windows.
echo.
echo Usage: installers\uninstall.bat [--purge] [--yes] [--help]
echo.
echo Removes the sancho CLI, library pointer, AI skills, and Claude Desktop MCP entry.
echo By default sancho-workspace\ ^(your .env, fetched-data, etc.^) is KEPT.
echo.
echo   --purge   Also delete sancho-workspace\
echo   --yes     Skip the interactive prompt
echo   --help    Show this message
endlocal
exit /b 0
