import datetime as dt

import pytest

from xauusd_trader import backtest
from xauusd_trader import journal

D = dt.datetime
DAY = D(2026, 1, 12)
SIG = {"time": "2026-01-12 08:50"}


def bar(hhmm, o, h, l, c):
    hh, mm = hhmm.split(":")
    return {"t": DAY.replace(hour=int(hh), minute=int(mm)), "o": o, "h": h, "l": l, "c": c}


def long_plan():
    return {"side": "long", "entry": 3350.0, "stop": 3345.0, "tp": 3361.05, "target_r": 2.0,
            "risk_per_oz": 5.35, "spread_used": 0.35}


def test_stop_wins_when_stop_and_target_in_same_bar(cfg):
    bars = [bar("08:50", 3350, 3362, 3344, 3355)]
    assert backtest.simulate(bars, SIG, long_plan(), cfg)[:2] == (-1.0, "sl")


def test_take_profit(cfg):
    bars = [bar("08:50", 3350, 3352, 3349, 3351), bar("08:55", 3351, 3362, 3350, 3361)]
    assert backtest.simulate(bars, SIG, long_plan(), cfg)[:2] == (2.0, "tp")


def test_bars_before_signal_are_ignored(cfg):
    bars = [bar("08:45", 3350, 3350, 3300, 3350), bar("08:50", 3350, 3352, 3349, 3351)]
    assert backtest.simulate(bars, SIG, long_plan(), cfg)[1] == "flat"


def test_flat_exit_ignores_bars_at_or_after_flat_time(cfg):
    bars = [bar("08:50", 3350, 3352, 3349, 3351), bar("16:30", 3351, 3370, 3350, 3369)]
    r, why, _ = backtest.simulate(bars, SIG, long_plan(), cfg)
    assert why == "flat"
    assert r == pytest.approx((3351 - 3350.35) / 5.35, abs=0.01)


def test_short_stop_is_hit_on_the_ask(cfg):
    p = {"side": "short", "entry": 3350.0, "stop": 3355.0, "tp": 3340.0, "target_r": 2.0,
         "risk_per_oz": 5.0, "spread_used": 0.35}
    bars = [bar("08:50", 3350, 3354.8, 3349, 3351)]       # high + spread = 3355.15 >= stop
    assert backtest.simulate(bars, SIG, p, cfg)[:2] == (-1.0, "sl")


def test_journal_stats():
    rows = [
        {"exit": "1", "r_multiple": "2", "pnl_acct": "100"},
        {"exit": "1", "r_multiple": "-1", "pnl_acct": "-50"},
        {"exit": "1", "r_multiple": "-1", "pnl_acct": "-50"},
        {"exit": "", "r_multiple": "", "pnl_acct": ""},   # open trades are excluded
    ]
    s = journal.stats(rows)
    assert s["n"] == 3
    assert s["win_rate"] == pytest.approx(1 / 3)
    assert s["total_r"] == pytest.approx(0)
    assert s["max_dd_r"] == pytest.approx(2)
    assert s["pf"] == pytest.approx(1.0)
    assert journal.stats([]) is None


def test_journal_roundtrip(tmp_path, monkeypatch):
    from xauusd_trader import common
    monkeypatch.setattr(common, "WORKDIR", str(tmp_path))
    journal.write([{"ticket": "1", "date_ny": "2026-01-12", "side": "long"}])
    rows = journal.read()
    assert rows[0]["ticket"] == "1" and rows[0]["exit"] == ""
