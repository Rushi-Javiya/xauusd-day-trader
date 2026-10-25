# News, risk check, journal

## news.json
Before trading, web-search today's USD high-impact releases and Fed speakers (CPI, NFP, PPI, retail sales, FOMC, jobless claims, Powell) and write `gold/news.json`:
`[{"time_ny": "2026-10-23 08:30", "title": "US CPI"}]`. Convert to New York time carefully and state the source. If you could not verify, say so; risk.py warns when the file is missing. Blackout is `news_before_min` before to `news_after_min` after each event.

## risk.py checks
Market open; inside the entry window; risk <= max loss per trade; reward:risk >= `min_rr`; trades today < max; worst case today (closed P&L minus open risk minus this trade) within the daily loss limit; not `max_consecutive_losses` losses in a row; news blackout. It writes `risk.json` with a hash of the plan. Any change to the plan invalidates the verdict. A PASS is valid `verdict_valid_min` minutes. BLOCK means no trade; report each reason; do not suggest ways around it.

## journal.py
`add --ticket N --fill PRICE` after a fill, `close --ticket N --exit PRICE --reason tp|sl|flat|manual [--pnl AMOUNT]` (pass the real P&L from MT5 history when available), `today`, `review` (win rate, avg R, profit factor, drawdown, split by setup/side/exit reason). Weekly, review honestly: with fewer than 30 closed trades, say the sample is too small to conclude anything.
