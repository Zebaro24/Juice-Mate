@echo off
REM template-managed: core/scripts/start-claude.bat - edit in _Claude-Template, not here
REM Open Claude Code at the project root, so CLAUDE.md, docs/ and .claude/ are in scope from the
REM first message. Inside Windows Terminal on purpose: there Shift+Enter is a real newline in the
REM prompt. Falls back to a plain PowerShell window if Windows Terminal is missing.

for %%I in ("%~dp0..") do set "ROOT=%%~fI"
for %%I in ("%ROOT%") do set "NAME=%%~nxI"

where wt.exe >nul 2>nul
if errorlevel 1 goto fallback

wt.exe -d "%ROOT%" --title "%NAME%" powershell -NoLogo -NoExit -ExecutionPolicy Bypass -Command claude
goto :eof

:fallback
start "%NAME% - Claude Code" powershell -NoLogo -NoExit -ExecutionPolicy Bypass -Command "Set-Location -LiteralPath '%ROOT%'; claude"
