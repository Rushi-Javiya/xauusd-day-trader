---
name: xauusd-day-trader
description: XAUUSD (gold) trading workflow for the New York session on MetaTrader 5. Finds key levels (previous day high/low, Asian and London ranges, opening range, round numbers), times entries (opening-range breakout, retest, liquidity sweep, long and short), sets stop and target in R, sizes lots to a max loss, runs a risk check (daily loss limit, news blackout, trade limits), backtests the rules on history, sends orders through the MT5 MCP server only after explicit approval, and keeps a trade journal. Use whenever the user mentions XAUUSD, gold trading, MT5, lot size for gold, stop loss or take profit on gold, the New York open, opening range, a gold backtest, or reviewing gold trades, even if they do not name this skill.
---

# XAUUSD day trader (New York session, MT5)

Gold only. Not for stocks or other symbols. All times are **New York time** unless stated. Berlin is usually New York + 6h, so 08:30 NY = 14:30 Berlin (the gap is 5h for about two weeks in March and again around late October/early November when the US and EU clocks change on different dates).

## Hard rules (never break these)
1. **No order without all three:** `risk.py` printed PASS for this exact plan, the user typed an explicit yes for this exact ticket, and the MCP order tool was approved in the app. Missing any one means no order.
2. **Demo account first.** Do not suggest going live until the journal has 50+ demo trades and the user has seen the backtest warnings.
3. **Never ask for or store passwords in chat.** Credentials go only into the user's own MT5 / Claude Desktop session.
4. **No promises.** No "this will win", no win-rate guarantees. The backtest shows what rules did on past data, not what they will do.
5. **Never raise risk to make a trade fit.** If the lot size is below the broker minimum, say so and stop. The user decides about changing limits.
6. Do not chase stale signals (older than 2 bars). Do not move a stop further away after entry.

## Files
`scripts/` holds launchers for the tools in `src/xauusd_trader/` (Python 3.10+, standard library only; `fetch.py` also needs `pip install MetaTrader5` on Windows). Work files live in `gold/` (override with env var `GOLD_DIR`): `config.json`, `data/M5.json`, `levels.json`, `entry.json`, `plan.json`, `risk.json`, `news.json`, `journal.csv`.

If you can run commands (Claude Code, or a computer tool on the user's machine), run the scripts yourself. If not, give the user the exact command and ask them to paste the output. Never invent output.

## Workflow (one trade)
| Step | Command | Read |
|---|---|---|
| 0 Setup, once | edit `gold/config.json` | references/setup.md |
| 1 Data | `python scripts/fetch.py --tf M5 --days 30` | references/setup.md |
| 2 Levels | `python scripts/levels.py` | references/rules.md |
| 3 News | write `gold/news.json` from today's USD high-impact events (web search) | references/risk.md |
| 4 Entry | `python scripts/entry.py [--pick orb]` | references/rules.md |
| 5 Plan | `python scripts/plan.py --write` | references/rules.md |
| 6 Risk | `python scripts/risk.py` | references/risk.md |
| 7 Order | MT5 MCP: `order_check`, then `order_send` | references/broker.md |
| 8 Journal | `python scripts/journal.py add` / `close` / `review` | references/risk.md |
| Backtest | `python scripts/backtest.py --bars gold/data/M5.json` | references/backtest.md |

Read the reference file for a step before doing it the first time in a conversation. Present results in plain words: levels as a short list, a signal as one line, the plan as entry / stop / target / lots / max loss.

## Interpreting results
- `WAITING` means no action. `EXPIRED` means no trade today. `CONFLICT` means standing aside is fine.
- `REFUSED` from plan.py is a real answer, not an error to work around.
- A backtest with fewer than ~100 trades, or an avg-R range that straddles zero, proves nothing. Say so.
