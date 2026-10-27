@echo off
rem One-step launcher: double-click it, or type its full path (or just `trade` once this folder is on PATH).
rem Starts the agent against your MT5 demo account, with Claude news research and explanations,
rem and keeps checking after every 5-minute bar until a ticket appears or the entry window closes.
rem Extra arguments are passed through, e.g.:  trade --setups orb
cd /d "%~dp0"
".venv\Scripts\gold-agent.exe" --broker mcp --llm --llm-news --watch %*
echo.
pause
