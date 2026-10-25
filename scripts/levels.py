"""Key levels for the New York session: previous day H/L, Asian + London ranges, opening range, ATR, round numbers.
Usage: python scripts/levels.py --bars gold/data/M5.json [--date YYYY-MM-DD]"""
import argparse, datetime as dt
from common import *


def hi_lo(bs):
    return (max(b["h"] for b in bs), min(b["l"] for b in bs)) if bs else (None, None)


def good_days(by_day, before):
    return sorted(k for k, v in by_day.items() if k < before and len(v) >= 100)


def compute(by_day, date, cfg):
    day = by_day.get(date, [])
    d0 = dt.datetime.combine(date, dt.time(0))
    or_start = d0 + TD(minutes=hhmm(cfg["range_start"]))
    or_end = or_start + TD(minutes=cfg["range_minutes"])
    tf = TD(minutes=cfg["tf_minutes"])
    asian = [b for b in day if d0 - TD(hours=4) <= b["t"] < d0 + TD(hours=3)]
    london = [b for b in day if d0 + TD(hours=3) <= b["t"] < or_start]
    orb = [b for b in day if or_start <= b["t"] < or_end]
    gd = good_days(by_day, date)
    pdh = pdl = pdc = None
    if gd:
        pb = by_day[gd[-1]]
        pdh, pdl = hi_lo(pb)
        pdc = pb[-1]["c"]
    pre = [b for b in day if b["t"] < or_start]
    a5 = atr(pre[-15:]) if len(pre) > 2 else None
    ranges = [hi_lo(by_day[k])[0] - hi_lo(by_day[k])[1] for k in gd[-14:]]
    atr_d = sum(ranges) / len(ranges) if ranges else None
    ah, al = hi_lo(asian)
    lh, ll = hi_lo(london)
    oh, ol = hi_lo(orb)
    complete = bool(orb) and orb[-1]["t"] + tf >= or_end
    price = day[-1]["c"] if day else pdc
    rnd = []
    if price:
        base = round(price / 10) * 10
        for lv in range(int(base) - 30, int(base) + 31, 10):
            rnd.append({"price": lv, "big": lv % 50 == 0})
    return {
        "date": str(date), "symbol": cfg["symbol"],
        "pdh": pdh, "pdl": pdl, "pdc": pdc,
        "asian_high": ah, "asian_low": al, "london_high": lh, "london_low": ll,
        "or_start": iso(or_start), "or_end": iso(or_end),
        "or_high": oh, "or_low": ol,
        "or_range": (oh - ol) if oh is not None else None,
        "or_complete": complete,
        "atr5": round(a5, 3) if a5 else 1.5, "atr_daily": round(atr_d, 2) if atr_d else None,
        "last_price": price, "last_bar": iso(day[-1]["t"]) if day else None,
        "round_numbers": rnd,
    }


def show(lv):
    f = lambda x: "-" if x is None else "%.2f" % x
    print("XAUUSD levels for %s (New York time)" % lv["date"])
    print("  prev day  H %s  L %s  close %s" % (f(lv["pdh"]), f(lv["pdl"]), f(lv["pdc"])))
    print("  Asian     H %s  L %s" % (f(lv["asian_high"]), f(lv["asian_low"])))
    print("  London    H %s  L %s" % (f(lv["london_high"]), f(lv["london_low"])))
    st = "complete" if lv["or_complete"] else "still forming / no data"
    print("  Opening range %s-%s  H %s  L %s  size %s  (%s)" % (
        lv["or_start"][-5:], lv["or_end"][-5:], f(lv["or_high"]), f(lv["or_low"]), f(lv["or_range"]), st))
    print("  ATR(M5,14) %s   avg daily range (14d) %s" % (f(lv["atr5"]), f(lv["atr_daily"])))
    print("  last bar %s  price %s" % (lv["last_bar"], f(lv["last_price"])))
    big = [str(r["price"]) for r in lv["round_numbers"] if r["big"]]
    near = [str(r["price"]) for r in lv["round_numbers"]]
    print("  round numbers: %s   (big: %s)" % (", ".join(near), ", ".join(big) or "-"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bars", default=path("data", "M5.json"))
    ap.add_argument("--date")
    a = ap.parse_args()
    cfg = load_config()
    bars = load_bars(a.bars, cfg)
    by_day = group_days(bars)
    date = dt.date.fromisoformat(a.date) if a.date else day_key(bars[-1]["t"])
    lv = compute(by_day, date, cfg)
    save_json("levels.json", lv)
    show(lv)


if __name__ == "__main__":
    main()
