"""gold-doctor: read-only health check of config, API key, MT5 connection, feed clock and news file.
Places no orders and prints no account number or balance."""
import asyncio
import os
import sys
import time
from typing import List, Optional, Tuple

from ..common import load_config, now_ny, ny_to_utc, path
from ..risk import market_closed
from . import guard
from .broker import BrokerError, McpBroker
from .cli import describe_limits
from .llm import ClaudeLLM, load_env_file

Check = Tuple[str, str]          # (OK | WARN | FAIL, message)
NEWS_MAX_AGE_H = 20


def check_config(cfg: dict) -> List[Check]:
    out: List[Check] = []
    p = cfg.get("mt5_path") or os.environ.get("MT5_PATH")
    if not p:
        out.append(("FAIL", "mt5_path is not set in gold/config.json (full path to terminal64.exe)"))
    elif not os.path.exists(p):
        out.append(("FAIL", "mt5_path does not exist: %s" % p))
    else:
        out.append(("OK", "MT5 terminal found"))
    if cfg["contract_size_confirmed"]:
        out.append(("OK", "contract size %s oz/lot confirmed" % cfg["contract_size"]))
    else:
        out.append(("WARN", "contract_size_confirmed is false: the agent will refuse to size trades"))
    off = describe_limits(cfg)
    out.append(("OK", "limits OFF: %s" % off if off else "all limits on (defaults)"))
    out.append(("OK", "risk per trade %.2f%% of %s %s = %.0f" % (
        cfg["max_loss_per_trade_pct"], cfg["account_balance"], cfg["account_ccy"],
        cfg["account_balance"] * cfg["max_loss_per_trade_pct"] / 100)))
    return out


def check_news_file(file_path: str, now_epoch: Optional[float] = None) -> Check:
    """A news.json left over from an earlier day would give a false all-clear, so flag old files."""
    if not os.path.exists(file_path):
        return ("WARN", "no gold/news.json: --llm-news will research the calendar; otherwise the agent will not trade")
    age_h = ((now_epoch or time.time()) - os.path.getmtime(file_path)) / 3600
    if age_h > NEWS_MAX_AGE_H:
        return ("WARN", "gold/news.json is %.0f hours old: delete it or update it, an old file is a false all-clear" % age_h)
    return ("OK", "gold/news.json is recent (%.1f hours old)" % age_h)


async def check_api_key(cfg: dict) -> Check:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return ("WARN", "ANTHROPIC_API_KEY not set: --llm / --llm-news will not work")
    try:
        await ClaudeLLM(cfg["llm_model"]).complete("Reply with one word.", "ok?")
        return ("OK", "Anthropic API key works")
    except Exception as e:
        return ("FAIL", "Anthropic API call failed (%s): %s" % (type(e).__name__, str(e)[:100]))


async def check_broker(cfg: dict, tries: int = 4, wait_s: float = 10.0) -> List[Check]:
    out: List[Check] = []
    try:
        async with McpBroker(terminal_path=cfg.get("mt5_path") or None) as b:
            if not await b.initialize():
                return [("FAIL", "MT5 initialize failed: is the terminal installed and logged in?")]
            out.append(("OK", "connected to the MT5 terminal"))
            problems = guard.check_account(await b.account_info())
            out.append(("FAIL", problems[0]) if problems else ("OK", "demo account"))
            info = await b.symbol_info(cfg["symbol"])
            for pr in guard.check_symbol(info, cfg):
                out.append(("WARN", pr))
            if market_closed(now_ny()):
                out.append(("WARN", "market is closed now, so the feed clock cannot be checked"))
                return out
            for i in range(tries):
                tick = await b.tick(cfg["symbol"])
                mode, off = guard.detect_time_mode(tick["time"], ny_to_utc(now_ny()), cfg)
                if mode == cfg["bar_time_mode"]:
                    out.append(("OK", "feed clock matches the broker offset%s" % (
                        " (after waiting %ds for the terminal to sync)" % (i * wait_s) if i else "")))
                    break
                if i < tries - 1:
                    await asyncio.sleep(wait_s)
            else:
                out.append(("FAIL", "feed clock looks like %r (%+.1fh), config says %r" % (mode, off, cfg["bar_time_mode"])))
    except BrokerError as e:
        out.append(("FAIL", str(e)))
    return out


def render(checks: List[Check]) -> str:
    mark = {"OK": "[ OK ]", "WARN": "[WARN]", "FAIL": "[FAIL]"}
    return "\n".join("%s %s" % (mark[lvl], msg) for lvl, msg in checks)


async def run() -> int:
    load_env_file()
    cfg = load_config()
    checks = check_config(cfg) + [check_news_file(path("news.json")), await check_api_key(cfg)]
    checks += await check_broker(cfg)
    print(render(checks))
    failed = sum(1 for lvl, _ in checks if lvl == "FAIL")
    print("\n%s" % ("%d problem(s) must be fixed before trading." % failed if failed else "Ready to trade (warnings are optional)."))
    return 1 if failed else 0


def main(argv: Optional[list] = None) -> None:
    """gold-doctor: check the setup without trading."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)
    sys.exit(asyncio.run(run()))


if __name__ == "__main__":
    main()
