"""Risk manager. PASS or BLOCK for the plan in gold/plan.json. Writes gold/risk.json (a verdict tied to the exact plan).
Usage: python scripts/risk.py [--now "YYYY-MM-DD HH:MM"]   (New York time; default = real time)
News: put today's high-impact USD events in gold/news.json as [{"time_ny":"2026-10-23 08:30","title":"CPI"}]"""
import argparse, hashlib, json
from common import *
import journal


def plan_hash(p):
    return hashlib.sha256(json.dumps(p, sort_keys=True, default=str).encode()).hexdigest()[:16]


def market_closed(n):
    wd, m = n.weekday(), n.hour * 60 + n.minute
    return (wd == 5) or (wd == 4 and m >= 17 * 60) or (wd == 6 and m < 18 * 60) or (17 * 60 <= m < 18 * 60)


def evaluate(plan, cfg, n, rows, news):
    why = []
    m = n.hour * 60 + n.minute
    if market_closed(n):
        why.append("market closed at %s NY" % iso(n))
    lo, hi = hhmm(cfg["range_start"]) + cfg["range_minutes"], hhmm(cfg["entry_cutoff"])
    if not (lo <= m < hi):
        why.append("outside entry window %02d:%02d-%s NY (now %s)" % (lo // 60, lo % 60, cfg["entry_cutoff"], iso(n)[-5:]))
    if plan["risk_acct"] > plan["max_loss_allowed"] + 1e-6:
        why.append("risk %.2f exceeds max loss per trade %.2f" % (plan["risk_acct"], plan["max_loss_allowed"]))
    if plan["rr"] < cfg["min_rr"]:
        why.append("reward:risk %.2f below minimum %.2f" % (plan["rr"], cfg["min_rr"]))
    if not plan.get("stop"):
        why.append("no stop")
    today = [r for r in rows if r["date_ny"] == str(n.date())]
    if len(today) >= cfg["max_trades_per_day"]:
        why.append("already %d trades today (max %d)" % (len(today), cfg["max_trades_per_day"]))
    closed = [r for r in today if r["exit"] != ""]
    pnl = sum(journal.fnum(r["pnl_acct"]) for r in closed)
    open_risk = sum(journal.fnum(r["risk_acct"]) for r in today if r["exit"] == "")
    limit = cfg["account_balance"] * cfg["daily_loss_limit_pct"] / 100.0
    if pnl - open_risk - plan["risk_acct"] < -limit:
        why.append("worst case today %.2f would break daily loss limit -%.2f" % (pnl - open_risk - plan["risk_acct"], limit))
    k = cfg["max_consecutive_losses"]
    if len(closed) >= k and all(journal.fnum(r["r_multiple"]) < 0 for r in closed[-k:]):
        why.append("%d losses in a row today: stop trading for the day" % k)
    for ev in news:
        t = parse_iso(ev["time_ny"])
        if t - TD(minutes=cfg["news_before_min"]) <= n <= t + TD(minutes=cfg["news_after_min"]):
            why.append("news blackout: %s at %s NY" % (ev.get("title", "event"), ev["time_ny"][-5:]))
    return why


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--now")
    a = ap.parse_args()
    cfg = load_config()
    plan = load_json("plan.json")
    if not plan:
        print("No gold/plan.json. Run plan.py --write first."); return
    n = parse_iso(a.now) if a.now else now_ny()
    why = evaluate(plan, cfg, n, journal.read(), load_json("news.json", []))
    if load_json("news.json") is None:
        print("warning: no gold/news.json, so news was NOT checked. Add today's USD events before trusting PASS.")
    verdict = {"verdict": "BLOCK" if why else "PASS", "reasons": why, "plan_hash": plan_hash(plan),
               "checked_ny": iso(n), "valid_min": cfg["verdict_valid_min"]}
    save_json("risk.json", verdict)
    if why:
        print("BLOCK"); [print("  - " + w) for w in why]
    else:
        print("PASS  (%s %s %.2f lots, risk %.2f %s; valid %d min)" % (
            plan["side"], plan["symbol"], plan["lots"], plan["risk_acct"], plan["account_ccy"], cfg["verdict_valid_min"]))


if __name__ == "__main__":
    main()
