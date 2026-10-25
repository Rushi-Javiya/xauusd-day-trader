"""Make SYNTHETIC gold-like M5 bars (random walk) to test the toolkit without MT5. NOT real prices."""
import json, random, datetime as dt, sys
from common import *

def main(days=120, out=None):
    random.seed(11)
    cfg = load_config()
    utc = dt.datetime(2026, 1, 4, 23, 0)          # Sunday evening UTC
    end = utc + TD(days=days)
    px, rows = 3300.0, []
    while utc < end:
        ny = to_ny(utc)
        wd, m = ny.weekday(), ny.hour * 60 + ny.minute
        closed = wd == 5 or (wd == 4 and m >= 17 * 60) or (wd == 6 and m < 18 * 60) or (17 * 60 <= m < 18 * 60)
        if not closed:
            vol = 0.9 + (1.2 if 8 * 60 <= m <= 12 * 60 else 0.0)
            o = px
            c = o + random.gauss(0, vol)
            h = max(o, c) + abs(random.gauss(0, vol * 0.5))
            l = min(o, c) - abs(random.gauss(0, vol * 0.5))
            off = cfg["broker_offset_summer"] if us_dst(utc) else cfg["broker_offset_winter"]
            srv = utc + TD(hours=off)
            rows.append({"time": int((srv - dt.datetime(1970, 1, 1)).total_seconds()),
                         "open": round(o, 2), "high": round(h, 2), "low": round(l, 2), "close": round(c, 2)})
            px = c
        utc += TD(minutes=5)
    import os
    os.makedirs(path("data"), exist_ok=True)
    out = out or path("data", "M5.json")
    with open(out, "w") as f:
        json.dump(rows, f)
    print("wrote %d synthetic bars -> %s" % (len(rows), out))

if __name__ == "__main__":
    main(*(int(x) for x in sys.argv[1:2]))
