# Backtest

`python scripts/backtest.py --bars gold/data/M5.json --setups orb --target-r 2 --from 2026-01-01`
Replays the exact entry/stop/target rules per New York day, one trade per day (first signal), flat at `flat_by`. Costs: spread on entry, shorts stopped on the ask, and if stop and target both fall inside one bar the stop counts first (pessimistic by design). Output: totals, by setup, side and weekday, plus a bootstrap of the avg-R range.

How to use it honestly:
- Need 100+ trades (about 6-12 months of M5). Fewer = say it proves nothing.
- Do not tune parameters until the numbers look good. If you tune, tune on one period and confirm on a later, untouched period.
- Slicing by weekday or setup creates small samples that look meaningful by luck. Treat them as questions, not findings.
- Real fills are worse than this: slippage on news, requotes, spread widening at the open.
- Compare against the random-data check: `make_demo_data.py` data should come out near 0R. If it does not, something is wrong.
