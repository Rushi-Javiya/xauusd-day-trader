"""Append-only audit log (gold/agent_log.jsonl): every ticket shown, the decision, and the outcome.
Closing the terminal must never lose a ticket. `gold-tickets` prints it in readable form."""
import argparse
import json
import os
from typing import List, Optional

from ..common import ensure, iso, now_ny, path

LOG_NAME = "agent_log.jsonl"


def append(event: str, **fields) -> None:
    """Never raises: a logging problem must not interrupt trading logic."""
    try:
        ensure()
        rec = {"at_ny": iso(now_ny()), "event": event}
        rec.update(fields)
        with open(path(LOG_NAME), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, default=str) + "\n")
    except OSError:
        pass


def read() -> List[dict]:
    p = path(LOG_NAME)
    if not os.path.exists(p):
        return []
    out = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
    return out


def format_event(e: dict) -> str:
    kind, at = e.get("event"), e.get("at_ny", "?")
    if kind == "ticket":
        s = "[%s NY] TICKET: %s" % (at, e.get("summary"))
        if e.get("rationale"):
            s += "\n    WHY (model-written): %s" % e["rationale"]
        return s
    if kind == "decision":
        return "[%s NY] DECISION: %s" % (at, "approved (yes)" if e.get("approved") else "not approved")
    if kind == "outcome":
        why = "; ".join(e.get("reasons") or [])
        order = e.get("order")
        extra = " | MT5 order %s filled at %s" % (order.get("ticket"), order.get("price")) if order else ""
        return "[%s NY] OUTCOME: %s%s%s" % (at, e.get("outcome"), " (%s)" % why if why else "", extra)
    return "[%s NY] %s" % (at, kind)


def main(argv: Optional[list] = None) -> None:
    """gold-tickets: show the last tickets and outcomes the agent logged."""
    ap = argparse.ArgumentParser(description=main.__doc__)
    ap.add_argument("-n", type=int, default=20, help="how many log entries to show (default 20)")
    a = ap.parse_args(argv)
    events = read()
    if not events:
        print("Nothing logged yet (%s)." % path(LOG_NAME))
        return
    for e in events[-a.n:]:
        print(format_event(e))
