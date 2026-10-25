"""Replay the entry rules on history. One trade per day max (first signal). Honest about costs:
long pays the spread on entry, short is stopped on the ask; if stop and target fall in the same bar, the STOP counts first.
Usage: python scripts/backtest.py --bars gold/data/M5.json [--setups orb] [--stop hint] [--target-r 2]
                                  [--from 2026-01-01] [--to ...] [--spread 0.35]"""
import argparse, random
from common import *
import levels, strategy, plan as planmod


def simulate(day_bars, sig, p, cfg):
    t0 = parse_iso(sig["time"])
    d0 = parse_iso(levels_date(sig)).replace(hour=0, minute=0)
    flat = d0 + TD(minutes=hhmm(cfg["flat_by"]))
    sp, long_ = p["spread_used"], p["side"] == "long"
    st, tp, entry = p["stop"], p["tp"], p["entry"]
    last = None
    for b in day_bars:
        if b["t"] < t0:
            continue
        if b["t"] >= flat:
            break
        last = b
        hit_stop = (b["l"] <= st) if long_ else (b["h"] + sp >= st)
        hit_tp = (b["h"] >= tp) if long_ else (b["l"] + sp <= tp)
        if hit_stop:
            return -1.0, "sl", b["t"]
        if hit_tp:
            return p["target_r"], "tp", b["t"]
    if last is None:
        return None
    ex = last["c"]
    r = ((ex - (entry + sp)) if long_ else (entry - (ex + sp))) / p["risk_per_oz"]
    return round(r, 2), "flat", last["t"]


def levels_date(sig):
    return sig["time"][:10] + " 00:00"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bars", default=path("data", "M5.json"))
    ap.add_argument("--setups", default="orb,retest,sweep")
    ap.add_argument("--stop", default="hint")
    ap.add_argument("--target-r", type=float)
    ap.add_argument("--spread", type=float)
    ap.add_argument("--from", dest="d_from"); ap.add_argument("--to", dest="d_to")
    ap.add_argument("--all-signals", action="store_true", help="count every setup's signal, not just the first per day")
    a = ap.parse_args()
    cfg = load_config()
    bars = load_bars(a.bars, cfg)
    by_day = group_days(bars)
    trades = []
    for date in sorted(by_day):
        if date.weekday() > 4 or len(by_day[date]) < 100:
            continue
        if a.d_from and str(date) < a.d_from or a.d_to and str(date) > a.d_to:
            continue
        lv = levels.compute(by_day, date, cfg)
        sigs = strategy.find_signals(by_day[date], lv, cfg, tuple(a.setups.split(",")))
        if not a.all_signals:
            sigs = sigs[:1]
        for s in sigs:
            p, err = planmod.price_plan(s, cfg, a.stop, a.target_r, a.spread)
            if err:
                continue
            res = simulate(by_day[date], s, p, cfg)
            if res:
                r, why, t = res
                trades.append({"date": date, "setup": s["setup"], "side": s["side"], "r": r, "why": why})
    if not trades:
        print("No trades found. Need several months of M5 data (>= 100 bars/day) and setups that fire."); return
    rs = [t["r"] for t in trades]
    def summary(ts, label):
        x = [t["r"] for t in ts]
        w = [v for v in x if v > 0]; gl = -sum(v for v in x if v < 0)
        eq = peak = dd = 0.0
        for v in x:
            eq += v; peak = max(peak, eq); dd = max(dd, peak - eq)
        print("%-18s n=%3d win %3.0f%% avgR %+.2f totalR %+6.1f PF %s maxDD %.1fR" % (
            label, len(x), 100 * len(w) / len(x), sum(x) / len(x), sum(x),
            "inf" if not gl else "%.2f" % (sum(w) / gl), dd))
    print("XAUUSD backtest %s -> %s | setups %s | stop %s | target %.1fR | spread %.2f" % (
        trades[0]["date"], trades[-1]["date"], a.setups, a.stop,
        a.target_r or cfg["target_r"], a.spread if a.spread is not None else cfg["spread_usd"]))
    summary(trades, "ALL")
    for k in ("setup", "side"):
        for v in sorted({t[k] for t in trades}):
            summary([t for t in trades if t[k] == v], "%s=%s" % (k, v))
    for wd, name in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri"]):
        ts = [t for t in trades if t["date"].weekday() == wd]
        if ts:
            summary(ts, name)
    random.seed(7)
    n, avgs, dds = len(rs), [], []
    for _ in range(5000):
        samp = [random.choice(rs) for _ in range(n)]
        avgs.append(sum(samp) / n)
        eq = peak = dd = 0.0
        for v in samp:
            eq += v; peak = max(peak, eq); dd = max(dd, peak - eq)
        dds.append(dd)
    avgs.sort(); dds.sort()
    print("Bootstrap (5000 resamples of these %d trades): avg R plausible range %+.2f to %+.2f (90%%); "
          "chance true avg R <= 0: %.0f%%; 95th-percentile max drawdown %.1fR" % (
              n, avgs[int(0.05 * 5000)], avgs[int(0.95 * 5000)],
              100.0 * sum(1 for x in avgs if x <= 0) / 5000, dds[int(0.95 * 5000)]))
    print("(A wide range that straddles zero means the data cannot tell you whether there is an edge.)")
    if len(trades) < 100:
        print("WARNING: only %d trades. Fewer than ~100 is too few to trust. Do not size up on this." % len(trades))
    print("Test on data you did NOT tune on before believing any number here.")


if __name__ == "__main__":
    main()
