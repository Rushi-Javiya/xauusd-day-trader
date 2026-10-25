"""Plain-English trade rationale and journal review written by the LLM.

Inputs are numbers computed by the deterministic code. The output is display text only: it is shown to
the human and is not part of the plan hash, so it cannot change what is sent to the broker."""
import json
from typing import Optional

from .. import journal
from .llm import LLM

MAX_RATIONALE = 700

RATIONALE_SYSTEM = (
    "You explain a proposed gold (XAUUSD) day trade to the trader who must approve it. "
    "Use ONLY the numbers given. 3-4 plain sentences: what the setup is, which levels matter, what would "
    "invalidate it. No predictions, no guarantees, no advice to change size, stop or target. "
    "Mention that this is a demo account trade."
)

REVIEW_SYSTEM = (
    "You review a trader's journal honestly and concisely. Use ONLY the statistics and rows provided; do not "
    "compute new numbers. If fewer than 30 closed trades, say the sample is too small to conclude anything. "
    "Point out patterns as questions to investigate, not findings. No promises, no financial advice."
)


async def explain_trade(llm: LLM, state: dict, news_count: int) -> str:
    lv, sig, plan = state["levels"], state["signal"], state["plan"]
    facts = {
        "levels": {k: lv.get(k) for k in ("pdh", "pdl", "asian_high", "asian_low", "london_high", "london_low",
                                          "or_high", "or_low", "or_range", "atr5")},
        "signal": {k: sig.get(k) for k in ("setup", "side", "time", "entry", "level", "level_price")},
        "plan": {k: plan.get(k) for k in ("side", "entry", "stop", "tp", "target_r", "risk_per_oz", "spread_used",
                                          "lots", "risk_acct", "account_ccy")},
        "news_events_today": news_count,
        "notes": ["risk_per_oz includes the spread: longs fill at the ask, so risk_per_oz = entry + spread_used - "
                  "stop; shorts are stopped on the ask. A gap between entry-stop and risk_per_oz is the spread, "
                  "not an error.",
                  "take-profit is also shifted by the spread for longs."],
    }
    text = await llm.complete(RATIONALE_SYSTEM, json.dumps(facts, default=str))
    return " ".join(text.split())[:MAX_RATIONALE]


async def review_journal(llm: LLM, last_rows: int = 20) -> Optional[str]:
    rows = journal.read()
    closed = [r for r in rows if r.get("exit") not in ("", None)]
    if not closed:
        return None
    stats = {"all": journal.stats(rows)}
    for key in ("setup", "side", "reason"):
        for v in sorted({r[key] for r in rows if r.get(key)}):
            stats["%s=%s" % (key, v)] = journal.stats([r for r in rows if r[key] == v])
    payload = {"stats": stats, "closed_trades": len(closed),
               "recent_rows": [{k: r.get(k) for k in ("date_ny", "side", "setup", "lots", "r_multiple", "pnl_acct",
                                                      "reason", "note")} for r in closed[-last_rows:]]}
    return await llm.complete(REVIEW_SYSTEM, json.dumps(payload, default=str))
