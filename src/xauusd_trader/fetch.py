"""Pull bars from your running, logged-in MetaTrader 5 terminal (Windows) into gold/data/*.json.
Needs:  pip install MetaTrader5      (the terminal must be open and logged in; no password is used here)
Usage:  python scripts/fetch.py --tf M5 --days 120 [--symbol XAUUSD] [--keep-forming]
Also prints symbol info (contract size, lot step, digits, spread) and your broker's server-time offset."""
import argparse, datetime as dt, json
from .common import *


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol")
    ap.add_argument("--tf", default="M5", choices=["M1", "M5", "M15", "H1", "H4", "D1"])
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--keep-forming", action="store_true")
    a = ap.parse_args()
    try:
        import MetaTrader5 as mt5
    except ImportError:
        print("Install it first:  pip install MetaTrader5   (Windows only)"); return
    cfg = load_config()
    sym = a.symbol or cfg["symbol"]
    if not mt5.initialize():
        print("initialize failed:", mt5.last_error(), "- is MT5 open and logged in?"); return
    mt5.symbol_select(sym, True)
    info = mt5.symbol_info(sym)
    if info is None:
        print("symbol %r not found. Search Market Watch for your broker's gold name (GOLD, XAUUSD.m ...)." % sym); return
    tfm = {"M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5, "M15": mt5.TIMEFRAME_M15,
           "H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4, "D1": mt5.TIMEFRAME_D1}[a.tf]
    end = dt.datetime.now() + dt.timedelta(days=2)
    rates = mt5.copy_rates_range(sym, tfm, end - dt.timedelta(days=a.days + 2), end)
    if rates is None or len(rates) == 0:
        print("no data returned:", mt5.last_error()); return
    rows = [{"time": int(r["time"]), "open": float(r["open"]), "high": float(r["high"]),
             "low": float(r["low"]), "close": float(r["close"]), "tick_volume": int(r["tick_volume"])} for r in rates]
    if not a.keep_forming:
        rows = rows[:-1]
    ensure()
    import os
    os.makedirs(path("data"), exist_ok=True)
    out = path("data", "%s.json" % a.tf)
    with open(out, "w") as f:
        json.dump(rows, f)
    tick = mt5.symbol_info_tick(sym)
    print("saved %d %s bars -> %s" % (len(rows), a.tf, out))
    print("symbol %s | contract_size %s | volume_min %s step %s max %s | digits %s | spread now %s points (point=%s)" % (
        sym, info.trade_contract_size, info.volume_min, info.volume_step, info.volume_max, info.digits,
        info.spread, info.point))
    if tick:
        utc_now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
        off = (dt.datetime(1970, 1, 1) + dt.timedelta(seconds=tick.time) - utc_now).total_seconds() / 3600
        print("broker server time is about UTC%+.0f right now (only meaningful while the market is open)." % round(off))
        print("-> set broker_offset_winter / broker_offset_summer in gold/config.json to match (typically 2 and 3).")
    mt5.shutdown()


if __name__ == "__main__":
    main()
