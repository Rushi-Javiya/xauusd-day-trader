"""LangGraph workflow for one trade attempt.

preflight -> fetch_data -> compute_levels -> check_news -> find_entry -> make_plan -> risk_check
          -> explain_trade -> human_approval -> execute -> log_trade

Every node either advances or sets `outcome` (a terminal result) and the graph ends. Sizing, the risk
gate and order authorization are deterministic code; the only human step is `interrupt()` in `approval`.
Nothing before the interrupt has side effects, because LangGraph re-runs the node on resume."""
import operator
import datetime as dt
from dataclasses import dataclass, field
from typing import Annotated, Any, Callable, Dict, List, Optional, Sequence, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from .. import journal, levels, strategy
from .. import plan as planmod
from .. import risk
from ..common import TD, bars_from_rows, day_key, group_days, iso, load_json, ny_to_utc, parse_iso
from . import guard
from .broker import Broker, BrokerError
from .explain import explain_trade
from .llm import LLM
from .news import merge, research_news


class TradeState(TypedDict, total=False):
    symbol_info: dict
    bars: list
    levels: dict
    news: list
    signal: dict
    plan: dict
    rationale: str
    verdict: dict
    ticket: dict
    approval: dict
    order: dict
    outcome: str
    reasons: list
    log: Annotated[list, operator.add]


def _file_news() -> Optional[list]:
    return load_json("news.json")


@dataclass
class Deps:
    broker: Broker
    cfg: dict
    clock: Callable[[], dt.datetime]                       # New York time
    news_loader: Callable[[], Optional[list]] = _file_news
    setups: Sequence[str] = ("orb", "retest", "sweep")
    stale_bars: int = 2
    llm: Optional[LLM] = None          # explains the ticket; with llm_news also researches the calendar
    llm_news: bool = False
    log_trades: bool = True
    extra: dict = field(default_factory=dict)


def _end(outcome: str, reasons: Sequence[str] = (), msg: str = "") -> dict:
    out: Dict[str, Any] = {"outcome": outcome, "reasons": list(reasons)}
    if msg or reasons:
        out["log"] = [msg or "%s: %s" % (outcome, "; ".join(reasons))]
    return out


def build_nodes(d: Deps) -> Dict[str, Callable]:
    cfg, broker = d.cfg, d.broker
    sym = cfg["symbol"]
    tf = TD(minutes=cfg["tf_minutes"])

    async def preflight(state: TradeState):
        if not await broker.initialize():
            return _end("PREFLIGHT_FAILED", ["MT5 initialize failed; is the terminal open and logged in?"])
        acct = await broker.account_info()
        info = await broker.symbol_info(sym)
        problems = guard.check_account(acct) + guard.check_symbol(info, cfg)
        now = d.clock()
        if not broker.replay and not risk.market_closed(now):
            tick = await broker.tick(sym)
            mode, off = guard.detect_time_mode(tick["time"], ny_to_utc(now), cfg)
            if mode == "mismatch":
                problems.append("tick time is %+.1fh from UTC, matching neither broker offsets nor UTC; "
                                "fix broker_offset_* in config" % off)
            elif mode != cfg["bar_time_mode"]:
                problems.append("bar_time_mode is %r but the feed looks like %r; set bar_time_mode accordingly"
                                % (cfg["bar_time_mode"], mode))
        if problems:
            return _end("PREFLIGHT_FAILED", problems)
        notes = []
        bal = acct.get("balance")
        if bal and abs(float(bal) - cfg["account_balance"]) > 0.2 * cfg["account_balance"]:
            notes.append("note: account balance %.0f differs >20%% from config account_balance %.0f "
                         "(sizing uses config)" % (float(bal), cfg["account_balance"]))
        return {"symbol_info": info, "log": ["preflight ok: demo account, %s" % sym] + notes}

    async def fetch_data(state: TradeState):
        rows = await broker.rates(sym, cfg["tf_minutes"], cfg["history_bars"])
        bars = bars_from_rows(rows, cfg)
        if len(bars) < 100:
            return _end("NO_DATA", ["only %d bars returned" % len(bars)])
        age = d.clock() - (bars[-1]["t"] + tf)
        if not broker.replay and age > TD(minutes=3 * cfg["tf_minutes"]):
            return _end("STALE_DATA", ["newest completed bar closed %d min ago" % (age.total_seconds() // 60)])
        return {"bars": bars, "log": ["%d bars, last closes %s NY" % (len(bars), iso(bars[-1]["t"] + tf))]}

    async def levels_node(state: TradeState):
        bars = state["bars"]
        date = day_key(bars[-1]["t"])
        lv = levels.compute(group_days(bars), date, cfg)
        if not lv["or_complete"]:
            return {"levels": lv, **_end("WAITING", ["opening range %s-%s not finished" % (
                lv["or_start"][-5:], lv["or_end"][-5:])])}
        return {"levels": lv, "log": ["OR %.2f-%.2f (size %.2f)" % (lv["or_low"], lv["or_high"], lv["or_range"])]}

    async def news(state: TradeState):
        events = d.news_loader()
        notes: List[str] = []
        if d.llm is not None and d.llm_news:
            try:
                now = d.clock()
                cache = d.extra.get("news_cache")      # watch mode: don't repeat paid searches every bar
                fresh = cache is not None and now - cache["at"] < TD(minutes=60)
                found = cache["events"] if fresh else await research_news(d.llm, now)
                if not fresh:
                    d.extra["news_cache"] = {"at": now, "events": found}
                events, added = merge(events or [], found) if events is not None else (found, len(found))
                notes.append("LLM news research%s: %d event(s) found, %d not in news.json "
                             "(LLM-sourced, not human-verified)" % (" (cached)" if fresh else "", len(found), added))
            except Exception as e:  # any LLM/parse failure falls back to the file, never to "no news"
                notes.append("LLM news research failed (%s: %s); using news.json only" % (type(e).__name__, e))
        if events is None:
            if cfg.get("require_news_check", True):
                return _end("NEWS_UNCHECKED", ["gold/news.json missing: add today's USD high-impact events "
                                               "(use [] if there are none)"] + notes)
            return {"news": [], "log": ["news NOT checked (require_news_check is off)"] + notes}
        return {"news": events, "log": ["%d news events loaded" % len(events)] + notes}

    async def entry(state: TradeState):
        bars, lv = state["bars"], state["levels"]
        date = parse_iso(lv["or_start"]).date()
        sigs = strategy.find_signals(group_days(bars).get(date, []), lv, cfg, tuple(d.setups))
        now_complete = bars[-1]["t"] + tf
        for s in sigs:
            s["age_min"] = int((now_complete - parse_iso(s["time"])).total_seconds() // 60)
        fresh = [s for s in sigs if s["age_min"] <= d.stale_bars * cfg["tf_minutes"]]
        if not fresh:
            why = "signals exist but are stale" if sigs else "no signal yet"
            return _end("NO_SIGNAL", [why])
        if len({s["side"] for s in fresh}) > 1:
            return _end("CONFLICT", ["fresh signals point in opposite directions; standing aside"])
        s = fresh[-1]
        return {"signal": s, "log": ["signal %s %s entry ~%.2f" % (s["setup"], s["side"], s["entry"])]}

    async def plan_node(state: TradeState):
        p, err = planmod.price_plan(state["signal"], cfg)
        if err:
            return _end("REFUSED", [err])
        plan, err = planmod.size_plan(p, cfg)
        if err:
            return _end("REFUSED", [err])
        return {"plan": plan, "log": ["plan %s %.2f lots stop %.2f tp %.2f risk %.2f %s" % (
            plan["side"], plan["lots"], plan["stop"], plan["tp"], plan["risk_acct"], plan["account_ccy"])]}

    async def risk_node(state: TradeState):
        now = d.clock()
        why = risk.evaluate(state["plan"], cfg, now, journal.read(), state.get("news") or [])
        verdict = risk.make_verdict(state["plan"], cfg, now, why)
        if why:
            return {"verdict": verdict, **_end("BLOCKED", why)}
        return {"verdict": verdict, "log": ["risk PASS"]}

    async def explain(state: TradeState):
        if d.llm is None:
            return {}
        try:
            text = await explain_trade(d.llm, state, len(state.get("news") or []))
        except Exception as e:  # explanation is optional; never blocks or alters the trade
            return {"log": ["rationale unavailable (%s)" % type(e).__name__]}
        return {"rationale": text, "log": ["rationale written"]}

    async def approval(state: TradeState):
        p = state["plan"]
        ticket = {
            "ticket_hash": guard.ticket_hash(p),
            "rationale": state.get("rationale"),
            "summary": "%s %s %.2f lots @ ~%.2f | stop %.2f | take-profit %.2f (%.1fR) | max loss %.2f %s | flat by %s NY"
                       % (p["symbol"], p["side"].upper(), p["lots"], p["entry"], p["stop"], p["tp"],
                          p["target_r"], p["risk_acct"], p["account_ccy"], cfg["flat_by"]),
            "plan": p,
        }
        decision = interrupt(ticket)
        if not isinstance(decision, dict) or decision.get("approved") is not True:
            return {"ticket": ticket, "approval": {"approved": False}, **_end("REJECTED", ["not approved"])}
        return {"ticket": ticket, "approval": decision, "log": ["ticket approved"]}

    async def execute(state: TradeState):
        plan = state["plan"]
        now = d.clock()
        problems = guard.authorize(plan, state.get("verdict"), state.get("approval"), now, cfg)
        if problems:
            return _end("NOT_AUTHORIZED", problems)
        try:
            problems = guard.check_account(await broker.account_info())
            if problems:
                return _end("NOT_AUTHORIZED", problems)
            tick = await broker.tick(sym)
            problems = guard.check_drift(plan, tick, cfg)
            if problems:
                return _end("PRICE_MOVED", problems)
            req = guard.build_request(plan, tick, state["symbol_info"], cfg)
            chk = await broker.order_check(req)
            if chk.get("retcode") not in guard.CHECK_OK:
                return _end("ORDER_CHECK_FAILED", ["retcode %s: %s" % (chk.get("retcode"), chk.get("comment"))])
            res = await broker.order_send(req)
        except BrokerError as e:
            return _end("ORDER_FAILED", [str(e)])
        if res.get("retcode") not in guard.SEND_OK:
            return _end("ORDER_FAILED", ["retcode %s: %s" % (res.get("retcode"), res.get("comment"))])
        return {"order": {"request": req, "result": res}, "outcome": "ORDER_PLACED", "reasons": [],
                "log": ["order placed: ticket %s at %s" % (res.get("order"), res.get("price"))]}

    async def journal_node(state: TradeState):
        if not d.log_trades:
            return {}
        res = state["order"]["result"]
        journal.add_trade(state["plan"], res.get("order"), d.clock(), res.get("price"), note="agent")
        return {"log": ["journaled ticket %s" % res.get("order")]}

    # node names must differ from state keys (LangGraph rule)
    return {"preflight": preflight, "fetch_data": fetch_data, "compute_levels": levels_node,
            "check_news": news, "find_entry": entry, "make_plan": plan_node, "risk_check": risk_node,
            "explain_trade": explain, "human_approval": approval, "execute": execute, "log_trade": journal_node}


CHAIN: List[str] = ["preflight", "fetch_data", "compute_levels", "check_news", "find_entry", "make_plan",
                    "risk_check", "explain_trade", "human_approval", "execute"]


def build_graph(deps: Deps, checkpointer=None):
    g = StateGraph(TradeState)
    for name, fn in build_nodes(deps).items():
        g.add_node(name, fn)
    g.add_edge(START, CHAIN[0])
    for a, b in zip(CHAIN, CHAIN[1:]):
        g.add_conditional_edges(a, lambda s, nxt=b: END if s.get("outcome") else nxt, [b, END])
    g.add_conditional_edges("execute", lambda s: "log_trade" if s.get("outcome") == "ORDER_PLACED" else END,
                            ["log_trade", END])
    g.add_edge("log_trade", END)
    return g.compile(checkpointer=checkpointer or MemorySaver())
