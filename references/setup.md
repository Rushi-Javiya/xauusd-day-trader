# Setup

## config.json
Copy `config.example.json` to `gold/config.json` and edit. Fields that matter most:
- `symbol`: the broker's exact gold name (XAUUSD, GOLD, XAUUSD.m ...). Check Market Watch.
- `account_balance`, `max_loss_per_trade_pct` (default 1), `daily_loss_limit_pct` (default 2), `max_trades_per_day` (3).
- `account_ccy` and `account_ccy_per_usd`: gold is priced in USD. For a EUR account set `"account_ccy": "EUR"` and `account_ccy_per_usd` to EUR per 1 USD (e.g. 0.92). Update it now and then.
- `contract_size`, `volume_min`, `volume_step`: confirm with `get_symbol_info` (or `fetch.py` prints them). 1.00 lot = 100 oz on most brokers, so $1 move = $100 per lot.
- `spread_usd`: typical spread in dollars (35 points on a 2-digit gold quote = $0.35). Check your broker.
- `broker_offset_winter` / `broker_offset_summer`: broker server time vs UTC (commonly 2 and 3). A wrong value shifts every session by hours and silently breaks the opening range. `fetch.py` prints a measured offset while the market is open. Verify it.
- `range_start` (default 08:30 NY, when major US data lands), `range_minutes` 15, `entry_cutoff` 11:30, `flat_by` 16:30.

## Data
`python scripts/fetch.py --tf M5 --days 30` reads the user's open, logged-in MT5 terminal (Windows). It drops the still-forming bar so signals only use completed bars. For backtests use `--days 180` or more; MT5 may need to download history first (open an M5 XAUUSD chart and scroll back). Without MT5 you can use CSV exported from MT5 (`View > Symbols > Bars > Export`) via `--bars file.csv`.

`python scripts/make_demo_data.py 150` makes synthetic data to practice the commands. It is random noise, not gold history.

## MCP connection check
Server: [`mcp-metatrader5-server`](https://github.com/Qoyyuum/mcp-metatrader5-server) (`uvx --from mcp-metatrader5-server mt5mcp`). Call `initialize` to attach to the already logged-in MT5 terminal, then `get_account_info` and `get_symbol_info` for the symbol. Do **not** call `login` with a password in chat; log in inside the terminal itself. Confirm the account is a demo account (`trade_mode` 0) before anything else.

Bars via `copy_rates_from_pos(symbol, timeframe, start_pos, count)`: timeframe is integer minutes (M5 = 5) and `time` comes back as ISO 8601 labelled UTC. MT5 stamps bars in broker server time, so the label may be misleading. Compare one returned bar against the same candle on the terminal chart before trusting session levels.
