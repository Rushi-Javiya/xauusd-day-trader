"""Entry timer: checks the latest completed M5 bars for a New York-session signal.
Usage: python scripts/entry.py --bars gold/data/M5.json [--setups orb,retest,sweep] [--date YYYY-MM-DD]
Writes gold/entry.json (the newest signal). It never places an order."""
import argparse, datetime as dt
from common import *
import levels, strategy


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bars", default=path("data", "M5.json"))
    ap.add_argument("--setups", default="orb,retest,sweep")
    ap.add_argument("--date")
    ap.add_argument("--pick", help="setup name to write to entry.json (default: newest signal)")
    ap.add_argument("--stale-bars", type=int, default=2, help="signal older than this many bars is stale")
    a = ap.parse_args()
    cfg = load_config()
    bars = load_bars(a.bars, cfg)
    by_day = group_days(bars)
    date = dt.date.fromisoformat(a.date) if a.date else day_key(bars[-1]["t"])
    lv = levels.compute(by_day, date, cfg)
    save_json("levels.json", lv)
    last = bars[-1]["t"]
    tf = TD(minutes=cfg["tf_minutes"])
    now_complete = last + tf
    d0 = parse_iso(lv["or_start"]).replace(hour=0, minute=0)
    cutoff = d0 + TD(minutes=hhmm(cfg["entry_cutoff"]))
    print("XAUUSD entry check | session %s | last completed bar closes %s NY | price %.2f" % (
        date, iso(now_complete), bars[-1]["c"]))
    if not lv["or_complete"]:
        print("STATUS: WAITING - opening range %s-%s not finished (or no bars yet)." % (lv["or_start"][-5:], lv["or_end"][-5:]))
        return
    rng = lv["or_range"]
    if not (cfg["or_min_usd"] <= rng <= cfg["or_max_usd"]):
        print("note: opening range %.2f outside [%.1f, %.1f]; breakout setups skipped (sweep can still fire)." % (
            rng, cfg["or_min_usd"], cfg["or_max_usd"]))
    sigs = strategy.find_signals(by_day.get(date, []), lv, cfg, tuple(a.setups.split(",")))
    if not sigs:
        if now_complete >= cutoff:
            print("STATUS: EXPIRED - no signal before the %s cutoff. No trade today." % cfg["entry_cutoff"])
        else:
            print("STATUS: WAITING - range H %.2f / L %.2f, no signal yet. Cutoff %s NY." % (lv["or_high"], lv["or_low"], cfg["entry_cutoff"]))
        return
    for s in sigs:
        age = int((now_complete - parse_iso(s["time"])).total_seconds() // 60)
        s["age_min"] = age
        s["fresh"] = age <= a.stale_bars * cfg["tf_minutes"]
        extra = "  [%s %.2f]" % (s["level"], s["level_price"]) if "level" in s else ""
        print("SIGNAL %-6s %-5s at %s NY  entry ~%.2f  stop hint %.2f%s  (%s, %d min ago)" % (
            s["setup"], s["side"].upper(), s["time"][-5:], s["entry"], s["stop_hint"], extra,
            "FRESH" if s["fresh"] else "STALE - do not chase", age))
    if len({x["side"] for x in sigs}) > 1:
        print("CONFLICT: signals point in opposite directions. Standing aside is a valid choice; use --pick <setup> to choose deliberately.")
    newest = next((x for x in sigs if x["setup"] == a.pick), sigs[-1]) if a.pick else sigs[-1]
    save_json("entry.json", newest)
    print("wrote gold/entry.json (%s %s). Next: plan.py" % (newest["setup"], newest["side"]))


if __name__ == "__main__":
    main()
