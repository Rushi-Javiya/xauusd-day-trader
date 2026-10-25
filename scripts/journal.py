"""Trade journal + review. CSV at gold/journal.csv.
  python scripts/journal.py add --ticket 123 --fill 3351.20 [--note ...]     (after a fill, uses gold/plan.json)
  python scripts/journal.py close --ticket 123 --exit 3360.10 --reason tp|sl|flat|manual [--pnl ACCT_CCY]
  python scripts/journal.py today | review"""
import argparse, csv, os
from common import *

COLS = ["ticket", "date_ny", "open_ny", "side", "setup", "lots", "entry", "stop", "tp", "risk_acct",
        "exit", "close_ny", "reason", "r_multiple", "pnl_acct", "note"]


def read():
    p = path("journal.csv")
    if not os.path.exists(p):
        return []
    with open(p, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write(rows):
    ensure()
    with open(path("journal.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in COLS})


def fnum(x, d=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return d


def stats(rows):
    cl = [r for r in rows if r.get("exit") not in ("", None)]
    if not cl:
        return None
    rs = [fnum(r["r_multiple"]) for r in cl]
    pn = [fnum(r["pnl_acct"]) for r in cl]
    w = [x for x in rs if x > 0]
    l = [x for x in rs if x <= 0]
    eq = peak = dd = 0.0
    for x in rs:
        eq += x; peak = max(peak, eq); dd = max(dd, peak - eq)
    gp, gl = sum(x for x in pn if x > 0), -sum(x for x in pn if x < 0)
    return {"n": len(cl), "win_rate": len(w) / len(cl), "avg_r": sum(rs) / len(rs), "total_r": sum(rs),
            "pnl": sum(pn), "pf": (gp / gl) if gl else float("inf"), "max_dd_r": dd,
            "avg_win_r": (sum(w) / len(w)) if w else 0, "avg_loss_r": (sum(l) / len(l)) if l else 0}


def show(s, title):
    if not s:
        print(title, ": no closed trades"); return
    print("%s: %d trades | win rate %.0f%% | avg R %+.2f | total %+.1fR | P&L %+.2f | PF %s | max DD %.1fR | avg win %+.2fR avg loss %+.2fR" % (
        title, s["n"], s["win_rate"] * 100, s["avg_r"], s["total_r"], s["pnl"],
        "inf" if s["pf"] == float("inf") else "%.2f" % s["pf"], s["max_dd_r"], s["avg_win_r"], s["avg_loss_r"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["add", "close", "today", "review"])
    ap.add_argument("--ticket"); ap.add_argument("--fill", type=float); ap.add_argument("--exit", type=float)
    ap.add_argument("--reason", default="manual"); ap.add_argument("--pnl", type=float); ap.add_argument("--note", default="")
    a = ap.parse_args()
    cfg = load_config()
    rows = read()
    if a.cmd == "add":
        p = load_json("plan.json")
        if not p or not a.ticket:
            print("need gold/plan.json and --ticket"); return
        n = now_ny()
        rows.append({"ticket": a.ticket, "date_ny": str(n.date()), "open_ny": iso(n), "side": p["side"],
                     "setup": p["setup"], "lots": p["lots"], "entry": a.fill or p["entry"], "stop": p["stop"],
                     "tp": p["tp"], "risk_acct": p["risk_acct"], "note": a.note})
        write(rows); print("logged ticket", a.ticket)
    elif a.cmd == "close":
        r = next((x for x in rows if x["ticket"] == a.ticket and x["exit"] == ""), None)
        if not r:
            print("open ticket not found"); return
        d = 1 if r["side"] == "long" else -1
        e, s, x = fnum(r["entry"]), fnum(r["stop"]), a.exit
        risk_oz = abs(e - s) or 1
        move = (x - e) * d
        pnl_usd = move * fnum(r["lots"]) * cfg["contract_size"]
        r.update({"exit": x, "close_ny": iso(now_ny()), "reason": a.reason,
                  "r_multiple": round(move / risk_oz, 2),
                  "pnl_acct": round(a.pnl if a.pnl is not None else pnl_usd * cfg["account_ccy_per_usd"], 2)})
        write(rows)
        print("closed %s: %+.2fR, %+.2f %s" % (a.ticket, fnum(r["r_multiple"]), fnum(r["pnl_acct"]), cfg["account_ccy"]))
    elif a.cmd == "today":
        t = [r for r in rows if r["date_ny"] == str(now_ny().date())]
        show(stats(t), "today"); print("trades today: %d (open: %d)" % (len(t), sum(1 for r in t if r["exit"] == "")))
    else:
        show(stats(rows), "all time")
        for key in ("setup", "side", "reason"):
            for v in sorted({r[key] for r in rows if r.get(key)}):
                show(stats([r for r in rows if r[key] == v]), "  %s=%s" % (key, v))
        cl = [r for r in rows if r["exit"] != ""]
        if cl and len(cl) < 30:
            print("note: only %d closed trades. Too few to judge anything yet." % len(cl))


if __name__ == "__main__":
    main()
