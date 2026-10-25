"""Deterministic safety layer between the agent and the broker. Pure functions, no I/O, no LLM.

Every function returns a list of human-readable problems (empty = fine). The graph treats any
non-empty list as a hard stop; nothing here can be overridden by model output."""
import datetime as dt
from typing import Any, Dict, List, Optional, Tuple

from ..common import TD, parse_iso, parse_time, us_dst
from ..risk import plan_hash

ACTION_DEAL = 1
BUY, SELL = 0, 1
FILL_FOK, FILL_IOC, FILL_RETURN = 0, 1, 2
ACCOUNT_DEMO = 0
CHECK_OK = {0, 10009}
SEND_OK = {10009, 10010}


def ticket_hash(plan: dict) -> str:
    return plan_hash(plan)


def check_account(account: Dict[str, Any]) -> List[str]:
    if account.get("trade_mode") != ACCOUNT_DEMO:
        return ["account is not a demo account (trade_mode=%r); this agent only trades demo" % account.get("trade_mode")]
    return []


def check_symbol(info: Dict[str, Any], cfg: dict) -> List[str]:
    out = []
    cs = info.get("trade_contract_size")
    if cs is None:
        if not cfg.get("contract_size_confirmed"):
            out.append("broker did not report contract size; confirm it (usually 100 oz/lot) and set "
                       "contract_size_confirmed: true in gold/config.json")
    elif float(cs) != float(cfg["contract_size"]):
        out.append("config contract_size %s differs from broker %s" % (cfg["contract_size"], cs))
    vmin = info.get("volume_min")
    if vmin is not None and float(vmin) > float(cfg["volume_min"]) + 1e-9:
        out.append("broker min lot %s is above config volume_min %s" % (vmin, cfg["volume_min"]))
    vstep = info.get("volume_step")
    if vstep is not None and abs(float(vstep) - float(cfg["volume_step"])) > 1e-9:
        out.append("broker lot step %s differs from config volume_step %s" % (vstep, cfg["volume_step"]))
    return out


def filling_type(info: Dict[str, Any]) -> int:
    """Symbol `filling_mode` is a bit flag (1=FOK, 2=IOC allowed); order `type_filling` is an enum
    (0=FOK, 1=IOC, 2=RETURN). Prefer IOC, then FOK, else RETURN."""
    flags = int(info.get("filling_mode") or 0)
    if flags & 2:
        return FILL_IOC
    if flags & 1:
        return FILL_FOK
    return FILL_RETURN


def detect_time_mode(tick_label: Any, utc_now: dt.datetime, cfg: dict) -> Tuple[str, float]:
    """Compare the newest tick's stamp with the wall clock (only meaningful while the market is open).
    'server': stamp = broker server time (offset matches config). 'utc': stamp is already UTC.
    'mismatch': neither; session levels would be wrong."""
    measured = (parse_time(tick_label) - utc_now).total_seconds() / 3600.0
    expected = cfg["broker_offset_summer"] if us_dst(utc_now) else cfg["broker_offset_winter"]
    if abs(measured - expected) <= 0.75:
        return "server", float(expected)
    if abs(measured) <= 0.75:
        return "utc", 0.0
    return "mismatch", round(measured, 2)


def price_drift(plan: dict, tick: Dict[str, Any]) -> float:
    """Distance between the live executable price and the price the plan assumed."""
    if plan["side"] == "long":
        return abs(float(tick["ask"]) - (plan["entry"] + plan["spread_used"]))
    return abs(float(tick["bid"]) - plan["entry"])


def check_drift(plan: dict, tick: Dict[str, Any], cfg: dict) -> List[str]:
    d = price_drift(plan, tick)
    limit = cfg["max_price_drift_r"] * plan["risk_per_oz"]
    if d > limit:
        return ["price moved %.2f from plan (limit %.2f = %.2fx stop distance): re-plan, do not chase" % (
            d, limit, cfg["max_price_drift_r"])]
    return []


def build_request(plan: dict, tick: Dict[str, Any], info: Dict[str, Any], cfg: dict) -> Dict[str, Any]:
    """Market order built only from the approved plan plus the live price. Flat integer fields."""
    long_ = plan["side"] == "long"
    return {
        "action": ACTION_DEAL,
        "symbol": plan["symbol"],
        "volume": float(plan["lots"]),
        "type": BUY if long_ else SELL,
        "price": float(tick["ask"] if long_ else tick["bid"]),
        "sl": float(plan["stop"]),
        "tp": float(plan["tp"]),
        "deviation": 20,
        "magic": 777001,
        "comment": "xauusd-agent",
        "type_filling": filling_type(info),
    }


def authorize(plan: Optional[dict], verdict: Optional[dict], approval: Optional[dict],
              now_ny: dt.datetime, cfg: dict) -> List[str]:
    """The three conditions from the hard rules: risk PASS for this exact plan, explicit approval of
    this exact ticket. (The third, tool approval in the MCP client, is outside this process.)"""
    if not plan:
        return ["no plan"]
    h = ticket_hash(plan)
    out = []
    if not verdict or verdict.get("verdict") != "PASS":
        out.append("no PASS risk verdict")
    else:
        if verdict.get("plan_hash") != h:
            out.append("risk verdict belongs to a different plan")
        age = now_ny - parse_iso(verdict["checked_ny"])
        if age > TD(minutes=verdict.get("valid_min", cfg["verdict_valid_min"])):
            out.append("risk verdict expired (%d min old)" % (age.total_seconds() // 60))
    if not approval or approval.get("approved") is not True:
        out.append("ticket not approved")
    elif approval.get("ticket_hash") != h:
        out.append("approval is for a different ticket")
    return out
