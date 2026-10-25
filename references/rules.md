# Levels, entries, stops, sizing

## Levels (levels.py)
Trading day rolls at 17:00 NY. Reports previous-day high/low/close, Asian range (20:00-03:00), London range (03:00 to range start), opening range (default 08:30-08:45), ATR(M5,14), 14-day average daily range, and $10 round numbers ($50 marked big). Use them as context and as the targets of sweeps.

## Entries (entry.py, strategy.py), all on completed M5 bars, entry window = opening range end to `entry_cutoff`
- **orb**: first M5 close above the opening-range high (long) or below the low (short). Skipped if the range is smaller than `or_min_usd` or larger than `or_max_usd` (too narrow = noise, too wide = stop too far).
- **retest**: after that break, price pulls back to the range edge (within `retest_tol_atr` x ATR) within `retest_max_bars` bars and a bar closes back in the break direction. Abandoned if price closes back inside.
- **sweep**: a bar pokes beyond PDH/PDL or the Asian/London high/low by at least `sweep_min_atr` x ATR and closes back inside. Trade the reversal.
Signals older than 2 bars are STALE. Do not chase. If signals point opposite ways, say so; standing aside is valid.

## Stops and targets (plan.py)
Stop modes: `hint` (default; per setup: range midpoint for orb, beyond the retest bar for retest, beyond the sweep extreme for sweep), `or-mid`, `or-opposite`, `atr:1.5`, `dist:3`, `price:3345`. Target = `target_r` x risk (default 2R). Spread is modelled: a long enters at the ask and is stopped on the bid; a short enters at the bid and is stopped on the ask. A stop tighter than `min_stop_usd` or 4x spread is refused.

## Sizing
lots = max loss / (contract_size x risk per oz x account_ccy_per_usd), rounded DOWN to the lot step. Below the broker minimum = REFUSED, never rounded up. Gold gaps and slippage can make real loss exceed the planned stop loss.
