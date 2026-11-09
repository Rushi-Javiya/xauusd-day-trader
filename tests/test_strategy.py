import datetime as dt

from xauusd_trader import strategy

D = dt.datetime
DAY = D(2026, 1, 12)


def bar(hhmm, o, h, l, c):
    hh, mm = hhmm.split(":")
    return {"t": DAY.replace(hour=int(hh), minute=int(mm)), "o": o, "h": h, "l": l, "c": c}


def levels(**kw):
    lv = {"or_complete": True, "or_start": "2026-01-12 08:30", "or_end": "2026-01-12 08:45",
          "or_high": 3350.0, "or_low": 3345.0, "atr5": 1.5, "pdh": None, "pdl": None,
          "asian_high": None, "asian_low": None, "london_high": None, "london_low": None}
    lv.update(kw)
    return lv


def test_no_signals_until_range_complete(cfg):
    assert strategy.find_signals([], levels(or_complete=False), cfg) == []


def test_orb_long_on_first_close_above_range(cfg):
    bars = [bar("08:45", 3349, 3351.5, 3348.9, 3351.0)]
    sigs = strategy.find_signals(bars, levels(), cfg, ("orb",))
    assert len(sigs) == 1
    s = sigs[0]
    assert (s["setup"], s["side"], s["entry"], s["time"]) == ("orb", "long", 3351.0, "2026-01-12 08:50")
    assert s["stop_hint"] == 3347.5


def test_orb_short_on_close_below_range(cfg):
    bars = [bar("08:45", 3346, 3346.2, 3343.0, 3344.0)]
    s = strategy.find_signals(bars, levels(), cfg, ("orb",))[0]
    assert s["side"] == "short"


def test_inside_range_gives_nothing(cfg):
    bars = [bar("08:45", 3347, 3349, 3346, 3348)]
    assert strategy.find_signals(bars, levels(), cfg, ("orb", "retest")) == []


def test_range_too_small_skips_breakouts_but_not_sweeps(cfg):
    lv = levels(or_high=3347.0, or_low=3345.0, pdh=3360.0)
    bars = [bar("08:45", 3347, 3348, 3346, 3347.5)]
    assert strategy.find_signals(bars, lv, cfg, ("orb", "retest")) == []
    bars = [bar("09:00", 3358, 3360.8, 3357, 3359.5)]
    assert strategy.find_signals(bars, lv, cfg, ("sweep",))[0]["setup"] == "sweep"


def test_retest_long(cfg):
    bars = [bar("08:45", 3349, 3351.5, 3348.9, 3351.0),
            bar("08:50", 3350.8, 3351.2, 3350.3, 3351.0)]
    s = strategy.find_signals(bars, levels(), cfg, ("retest",))[0]
    assert s["setup"] == "retest" and s["side"] == "long"
    assert s["stop_hint"] == 3349.7           # min(low, or_high) - buffer


def test_retest_abandoned_when_price_closes_back_inside(cfg):
    bars = [bar("08:45", 3349, 3351.5, 3348.9, 3351.0),
            bar("08:50", 3351, 3351, 3347, 3348.0),
            bar("08:55", 3348, 3351.2, 3350.3, 3351.0)]
    assert strategy.find_signals(bars, levels(), cfg, ("retest",)) == []


def test_sweep_short_above_pdh(cfg):
    lv = levels(pdh=3360.0)
    bars = [bar("09:00", 3358, 3360.8, 3357.5, 3359.5)]
    s = strategy.find_signals(bars, lv, cfg, ("sweep",))[0]
    assert s["side"] == "short" and s["level"] == "PDH"
    assert s["stop_hint"] == 3361.1


def test_sweep_too_shallow_is_ignored(cfg):
    lv = levels(pdh=3360.0)
    bars = [bar("09:00", 3358, 3360.1, 3357.5, 3359.5)]   # poke 0.1 < 0.25 * ATR
    assert strategy.find_signals(bars, lv, cfg, ("sweep",)) == []


def test_nothing_after_entry_cutoff(cfg):
    bars = [bar("11:30", 3349, 3351.5, 3348.9, 3351.0)]
    assert strategy.find_signals(bars, levels(), cfg, ("orb",)) == []

def test_entry_window_off_allows_signals_until_the_trading_day_ends(cfg):
    inside = [bar("%02d:%02d" % (h, m), 3347, 3349, 3346, 3348) for h in (8, 9, 10, 11, 12, 13) for m in range(0, 60, 5)
              if (h, m) >= (8, 45)]
    late_break = inside + [bar("14:00", 3349, 3352, 3348.9, 3351.5)]
    assert strategy.find_signals(late_break, levels(), cfg, ("orb",)) == []
    cfg["entry_window"] = False
    s = strategy.find_signals(late_break, levels(), cfg, ("orb",))
    assert len(s) == 1 and s[0]["time"] == "2026-01-12 14:05"


def test_session_cutoff(cfg):
    from xauusd_trader.common import session_cutoff
    assert session_cutoff(cfg) == "11:30"
    cfg["entry_window"] = False
    assert session_cutoff(cfg) == "17:00"
