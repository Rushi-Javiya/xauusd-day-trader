"""Exit planner + lot sizer. Sets stop and target in R, sizes lots to your max loss, or refuses.
Usage: python scripts/plan.py [--stop hint|or-mid|or-opposite|atr:1.5|dist:3.0|price:3345.5]
                              [--target-r 2] [--spread 0.35] [--balance N] [--write]
       (reads gold/entry.json; or give --side long|short --entry PRICE --stop dist:/price:)
Spread model: long enters at ask (= price + spread) and is stopped on bid; short enters at bid and is stopped on ask."""
import argparse, math
from common import *


def price_plan(sig, cfg, stop="hint", target_r=None, spread=None):
    """Returns (plan, None) or (None, reason). No lot sizing here."""
    side, entry = sig["side"], float(sig["entry"])
    sp = cfg["spread_usd"] if spread is None else spread
    tr = cfg["target_r"] if target_r is None else target_r
    buf = cfg["stop_buffer_usd"]
    long_ = side == "long"
    if stop == "hint":
        st = sig.get("stop_hint")
    elif stop == "or-mid":
        st = (sig["or_high"] + sig["or_low"]) / 2
    elif stop == "or-opposite":
        st = sig["or_low"] - buf if long_ else sig["or_high"] + buf
    elif stop.startswith("atr:"):
        d = float(stop[4:]) * sig["atr5"]
        st = entry - d if long_ else entry + d
    elif stop.startswith("dist:"):
        d = float(stop[5:])
        st = entry - d if long_ else entry + d
    elif stop.startswith("price:"):
        st = float(stop[6:])
    else:
        return None, "unknown stop mode %r" % stop
    if st is None:
        return None, "no stop available"
    st = round(st, cfg["digits"])
    if long_ and st >= entry:
        return None, "REFUSED: long stop %.2f is at or above entry %.2f" % (st, entry)
    if not long_ and st <= entry:
        return None, "REFUSED: short stop %.2f is at or below entry %.2f" % (st, entry)
    risk = (entry + sp - st) if long_ else (st - entry)     # dollars per oz at the stop
    if risk < cfg["min_stop_usd"] or risk < cfg["min_stop_spread_mult"] * sp:
        return None, "REFUSED: stop too tight (risk %.2f/oz; need >= %.2f and >= %.1fx spread)" % (
            risk, cfg["min_stop_usd"], cfg["min_stop_spread_mult"])
    tp = (entry + sp + tr * risk) if long_ else (entry - tr * risk)
    tp1 = (entry + sp + risk) if long_ else (entry - risk)
    return {"setup": sig.get("setup", "manual"), "side": side, "entry": round(entry, cfg["digits"]),
            "stop": st, "tp": round(tp, cfg["digits"]), "tp_1r": round(tp1, cfg["digits"]),
            "target_r": tr, "rr": tr, "risk_per_oz": round(risk, 2), "spread_used": sp,
            "signal_time": sig.get("time")}, None


def size_plan(p, cfg, balance=None):
    bal = cfg["account_balance"] if balance is None else balance
    max_loss = bal * cfg["max_loss_per_trade_pct"] / 100.0           # account currency
    per_lot = cfg["contract_size"] * p["risk_per_oz"] * cfg["account_ccy_per_usd"]
    raw = max_loss / per_lot
    step = cfg["volume_step"]
    lots = math.floor(raw / step + 1e-9) * step
    lots = round(min(lots, cfg["volume_max"]), 2)
    if lots < cfg["volume_min"]:
        need = per_lot * cfg["volume_min"]
        return None, ("REFUSED: smallest lot (%.2f) risks %.2f %s at this stop, above your max loss of %.2f %s. "
                      "Use a tighter valid stop, a bigger balance, or accept a higher %% (your call, not auto-bumped)." % (
                          cfg["volume_min"], need, cfg["account_ccy"], max_loss, cfg["account_ccy"]))
    out = dict(p)
    out.update({"lots": lots, "risk_acct": round(lots * per_lot, 2), "max_loss_allowed": round(max_loss, 2),
                "account_ccy": cfg["account_ccy"], "balance": bal, "symbol": cfg["symbol"],
                "contract_size": cfg["contract_size"],
                "created_ny": iso(now_ny())})
    return out, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--entry-json", default=path("entry.json"))
    ap.add_argument("--stop", default="hint")
    ap.add_argument("--target-r", type=float)
    ap.add_argument("--spread", type=float)
    ap.add_argument("--balance", type=float)
    ap.add_argument("--side")
    ap.add_argument("--entry", type=float)
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    cfg = load_config()
    if a.side and a.entry:
        sig = {"side": a.side, "entry": a.entry, "setup": "manual", "atr5": 1.5,
               "or_high": a.entry, "or_low": a.entry}
    else:
        sig = load_json(os.path.basename(a.entry_json))
        if not sig:
            print("No entry.json found. Run entry.py first, or pass --side and --entry."); return
    p, err = price_plan(sig, cfg, a.stop, a.target_r, a.spread)
    if err:
        print(err); return
    plan, err = size_plan(p, cfg, a.balance)
    if err:
        print(err); return
    print("PLAN %s %s %s" % (plan["symbol"], plan["side"].upper(), plan["setup"]))
    print("  entry ~%.2f   stop %.2f   take-profit %.2f (%.1fR)   1R at %.2f" % (
        plan["entry"], plan["stop"], plan["tp"], plan["target_r"], plan["tp_1r"]))
    print("  risk %.2f $/oz  ->  %.2f lots  ->  max loss at stop %.2f %s (allowed %.2f)" % (
        plan["risk_per_oz"], plan["lots"], plan["risk_acct"], plan["account_ccy"], plan["max_loss_allowed"]))
    print("  1 lot = %d oz, so a $1 move = $%d per lot. Flat by %s NY." % (
        plan["contract_size"], plan["contract_size"], cfg["flat_by"]))
    if a.write:
        save_json("plan.json", plan)
        print("wrote gold/plan.json. Next: risk.py")


if __name__ == "__main__":
    main()
