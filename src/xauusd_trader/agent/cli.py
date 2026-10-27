"""Run the LangGraph trade agent.

  gold-agent --broker paper --data gold/data/M5.json --now "2026-03-10 08:55" [--auto-approve]
  gold-agent --broker mcp                      # real MT5 MCP server, demo account only: one check
  gold-agent --broker mcp --watch              # re-check after every bar until a ticket or the cutoff

You are shown the exact ticket and must type `yes`. Anything else sends nothing."""
import argparse
import asyncio
import contextlib
import datetime as dt
import json
import sys
import time
import uuid

from langgraph.types import Command

from ..common import TD, hhmm, load_config, now_ny, parse_iso
from .broker import McpBroker, PaperBroker
from .explain import review_journal
from .graph import Deps, build_graph
from .llm import ClaudeLLM, load_env_file


def _show(res: dict, skip: int = 0) -> int:
    """Print log lines after the first `skip`; returns how many lines exist now."""
    lines = res.get("log", [])
    for line in lines[skip:]:
        print("  - " + line)
    return len(lines)


def _print_outcome(res: dict) -> None:
    why = res.get("reasons") or []
    print("\nOUTCOME: %s%s" % (res.get("outcome"), " (%s)" % "; ".join(why) if why else ""))


GOOD_EXIT = {"ORDER_PLACED", "NO_SIGNAL", "WAITING", "CONFLICT", "REJECTED"}
RETRY_OUTCOMES = {"WAITING", "NO_SIGNAL", "CONFLICT", "STALE_DATA", "PRICE_MOVED"}
TRANSIENT_BLOCKS = ("news blackout", "outside entry window")


def window_end(now: dt.datetime, cfg: dict) -> dt.datetime:
    return now.replace(hour=0, minute=0, second=0, microsecond=0) + TD(minutes=hhmm(cfg["entry_cutoff"]))


def retryable(res: dict, now: dt.datetime, cfg: dict) -> bool:
    """Should --watch try again on the next bar? Only for outcomes that can change by themselves, and only
    while the entry window is still open. Anything final (refused plan, failed preflight, rejected ticket,
    placed order, trade-count or loss limits) stops the loop."""
    if now >= window_end(now, cfg):
        return False
    outcome = res.get("outcome")
    if outcome in RETRY_OUTCOMES:
        return True
    if outcome == "BLOCKED":
        return all(r.startswith(TRANSIENT_BLOCKS) for r in res.get("reasons") or [])
    return False


def seconds_to_next_bar(epoch: float, tf_min: int, grace: int = 15) -> float:
    """Seconds until the next bar boundary plus a grace period so the broker has closed the bar."""
    step = tf_min * 60
    return step - (epoch % step) + grace


async def attempt(deps: Deps, args, watch: bool):
    """One pass through the graph, including the approval prompt. Returns (result, done)."""
    graph = build_graph(deps)
    thread = {"configurable": {"thread_id": str(uuid.uuid4())}}
    res = await graph.ainvoke({"log": []}, thread)
    if "__interrupt__" not in res:
        if watch and retryable(res, deps.clock(), deps.cfg):
            return res, False
        _show(res)
        _print_outcome(res)
        return res, True
    shown = _show(res)
    ticket = res["__interrupt__"][0].value
    print("\nTICKET: " + ticket["summary"])
    if ticket.get("rationale"):
        print("WHY (written by the model, display only): " + ticket["rationale"])
    if args.auto_approve:
        answer = "yes"
    else:
        answer = input("Type yes to send this exact order to the demo account: ").strip().lower()
    decision = {"approved": answer == "yes", "ticket_hash": ticket["ticket_hash"]}
    res = await graph.ainvoke(Command(resume=decision), thread)
    _show(res, shown)
    _print_outcome(res)
    return res, True


async def run(args) -> int:
    load_env_file()
    cfg = load_config()
    if args.no_news_check:
        cfg["require_news_check"] = False
    if args.watch and args.broker != "mcp":
        print("--watch only makes sense with --broker mcp"); return 2
    llm = None
    if args.llm or args.llm_news:
        try:
            llm = ClaudeLLM(cfg["llm_model"], cfg["llm_news_model"])
        except RuntimeError as e:
            print(e); return 2
    clock = now_ny
    async with contextlib.AsyncExitStack() as stack:
        if args.broker == "paper":
            if not args.data:
                print("--data is required with --broker paper"); return 2
            with open(args.data, encoding="utf-8-sig") as f:
                data = json.load(f)
            as_of = parse_iso(args.now) if args.now else None
            broker = PaperBroker(data["bars"] if isinstance(data, dict) else data, cfg, as_of_ny=as_of)
            if as_of:
                clock = lambda: as_of  # noqa: E731
        else:
            if args.auto_approve:
                print("--auto-approve is only allowed with --broker paper"); return 2
            broker = await stack.enter_async_context(McpBroker(
                command=args.mcp_command, args=args.mcp_arg or None, terminal_path=cfg.get("mt5_path") or None))
        deps = Deps(broker=broker, cfg=cfg, clock=clock, setups=tuple(args.setups.split(",")),
                    llm=llm, llm_news=args.llm_news)
        if args.watch:
            print("Watching until %s NY, checking after every %d-minute bar. Ctrl+C to stop." % (
                cfg["entry_cutoff"], cfg["tf_minutes"]))
        while True:
            res, done = await attempt(deps, args, args.watch)
            if done:
                return 0 if res.get("outcome") in GOOD_EXIT else 1
            now = deps.clock()
            why = "; ".join(res.get("reasons") or [])
            print("[%s NY] %s%s" % (now.strftime("%H:%M"), res.get("outcome"), " - " + why if why else ""))
            await asyncio.sleep(seconds_to_next_bar(time.time(), cfg["tf_minutes"]))


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--broker", choices=["paper", "mcp"], default="paper")
    ap.add_argument("--data", help="paper broker: M5 bars JSON (MT5 rows)")
    ap.add_argument("--now", help='paper broker: replay as of "YYYY-MM-DD HH:MM" New York time')
    ap.add_argument("--setups", default="orb,retest,sweep")
    ap.add_argument("--auto-approve", action="store_true", help="paper broker only: approve without asking")
    ap.add_argument("--no-news-check", action="store_true", help="do not require gold/news.json (not recommended)")
    ap.add_argument("--llm", action="store_true", help="Claude writes a short rationale shown with the ticket")
    ap.add_argument("--llm-news", action="store_true",
                    help="Claude researches today's USD events (web search) and adds them as blackouts")
    ap.add_argument("--watch", action="store_true",
                    help="mcp only: re-check after every bar until a ticket appears or the entry window closes")
    ap.add_argument("--mcp-command", default="uvx")
    ap.add_argument("--mcp-arg", action="append", help="repeatable; default: --from mcp-metatrader5-server --with pydantic<2.12 mt5mcp")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)     # show progress immediately, even when piped
    try:
        sys.exit(asyncio.run(run(ap.parse_args(argv))))
    except KeyboardInterrupt:
        print("\nStopped. Nothing was sent.")
        sys.exit(130)

def review_main(argv=None) -> None:
    """gold-review: Claude reviews gold/journal.csv using the deterministic statistics as input."""
    argparse.ArgumentParser(description=review_main.__doc__).parse_args(argv)
    load_env_file()
    cfg = load_config()
    try:
        llm = ClaudeLLM(cfg["llm_model"], cfg["llm_news_model"])
    except RuntimeError as e:
        print(e); sys.exit(2)
    text = asyncio.run(review_journal(llm))
    print(text if text else "No closed trades in the journal yet.")


if __name__ == "__main__":
    main()
