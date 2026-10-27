@echo off
rem One-step launcher: double-click it, or type its full path.
rem Runs the agent against your MT5 demo account, with Claude news research and explanations, and keeps
rem running by itself: it sleeps outside the New York session, wakes before each weekday session, checks
rem after every 5-minute bar, shows a ticket when a valid setup appears, then waits for the next day.
rem Keep this window open, MT5 open and logged in, and the PC awake. Ctrl+C stops it.
rem Extra arguments are passed through, e.g.:  trade.bat --setups orb
cd /d "%~dp0"
".venv\Scripts\gold-agent.exe" --broker mcp --llm --llm-news --always-on %*
echo.
pause
