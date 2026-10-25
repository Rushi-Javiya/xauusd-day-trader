"""Entry rules for the New York session on M5 bars. Used by entry.py (live) and backtest.py (history).
Setups: orb (opening-range breakout), retest (break then pullback), sweep (liquidity sweep reversal)."""
from common import *


def _sig(setup, side, bar, tf, entry, stop_hint, lv, extra=None):
    s = {"setup": setup, "side": side, "time": iso(bar["t"] + TD(minutes=tf)),
         "bar_time": iso(bar["t"]), "entry": entry, "stop_hint": round(stop_hint, 2),
         "or_high": lv["or_high"], "or_low": lv["or_low"], "atr5": lv["atr5"]}
    if extra:
        s.update(extra)
    return s


def find_signals(day_bars, lv, cfg, setups=("orb", "retest", "sweep")):
    out = []
    if not lv.get("or_complete"):
        return out
    tf = cfg["tf_minutes"]
    or_end = parse_iso(lv["or_end"])
    d0 = parse_iso(lv["or_start"]).replace(hour=0, minute=0)
    cutoff = d0 + TD(minutes=hhmm(cfg["entry_cutoff"]))
    orh, orl, atr5 = lv["or_high"], lv["or_low"], lv["atr5"]
    buf = cfg["stop_buffer_usd"]
    post = [b for b in day_bars if or_end <= b["t"] < cutoff]
    size_ok = cfg["or_min_usd"] <= (orh - orl) <= cfg["or_max_usd"]

    # find the first close outside the range
    brk = None
    for i, b in enumerate(post):
        if b["c"] > orh:
            brk = (i, "long"); break
        if b["c"] < orl:
            brk = (i, "short"); break

    if size_ok and brk and "orb" in setups:
        i, side = brk
        b = post[i]
        out.append(_sig("orb", side, b, tf, b["c"], (orh + orl) / 2, lv))

    if size_ok and brk and "retest" in setups:
        i, side = brk
        tol = cfg["retest_tol_atr"] * atr5
        for b in post[i + 1: i + 1 + cfg["retest_max_bars"]]:
            if side == "long":
                if b["c"] < orh - tol:
                    break
                if b["l"] <= orh + tol and b["c"] > orh and b["c"] > b["o"]:
                    out.append(_sig("retest", side, b, tf, b["c"], min(b["l"], orh) - buf, lv)); break
            else:
                if b["c"] > orl + tol:
                    break
                if b["h"] >= orl - tol and b["c"] < orl and b["c"] < b["o"]:
                    out.append(_sig("retest", side, b, tf, b["c"], max(b["h"], orl) + buf, lv)); break

    if "sweep" in setups:
        highs = [("PDH", lv["pdh"]), ("Asian high", lv["asian_high"]), ("London high", lv["london_high"])]
        lows = [("PDL", lv["pdl"]), ("Asian low", lv["asian_low"]), ("London low", lv["london_low"])]
        found = None
        for b in post:
            for name, L in highs:
                if L is not None and b["h"] > L and b["c"] < L and (b["h"] - L) >= cfg["sweep_min_atr"] * atr5:
                    found = _sig("sweep", "short", b, tf, b["c"], b["h"] + buf, lv, {"level": name, "level_price": L}); break
            if not found:
                for name, L in lows:
                    if L is not None and b["l"] < L and b["c"] > L and (L - b["l"]) >= cfg["sweep_min_atr"] * atr5:
                        found = _sig("sweep", "long", b, tf, b["c"], b["l"] - buf, lv, {"level": name, "level_price": L}); break
            if found:
                break
        if found:
            out.append(found)
    out.sort(key=lambda s: s["time"])
    return out
