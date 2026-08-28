@echo off
REM Checkout convenience wrapper for Sancho's shared, ownership-aware uninstall.
REM
REM Normal cleanup:
REM   installers\uninstall.bat
REM
REM Explicitly purge one workspace (data deletion):
REM   installers\uninstall.bat --purge-workspace --workspace C:\exact\sancho-workspace --workspace-id UUID --yes
REM
REM This wrapper never removes the running CLI. The shared command prints
REM `uv tool uninstall sancho-fetch` last after integrations are detached.

where sancho >NUL 2>&1
if errorlevel 1 (
  echo The Sancho CLI is required so ownership can be checked safely. 1>&2
  echo Install the checkout first with: installers\setup.bat 1>&2
  exit /b 1
)

sancho uninstall %*
exit /b %ERRORLEVEL%
