import asyncio
from types import SimpleNamespace

import pytest

pytest.importorskip("langgraph")

from xauusd_trader import common  # noqa: E402
from xauusd_trader.agent import audit  # noqa: E402
from xauusd_trader.agent.cli import attempt  # noqa: E402


def test_append_and_read_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "WORKDIR", str(tmp_path))
    audit.append("ticket", summary="XAUUSD SHORT 1 lots", plan={"lots": 1})
    audit.append("outcome", outcome="NO_SIGNAL", reasons=["x"], order=None)
    events = audit.read()
    assert [e["event"] for e in events] == ["ticket", "outcome"]
    assert events[0]["plan"] == {"lots": 1} and events[0]["at_ny"]


def test_read_skips_corrupt_lines(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "WORKDIR", str(tmp_path))
    (tmp_path / audit.LOG_NAME).write_text('{"event": "ticket", "summary": "a"}\nnot json\n{"event": "decision"}\n')
    assert [e["event"] for e in audit.read()] == ["ticket", "decision"]


def test_logging_failure_never_raises(tmp_path, monkeypatch):
    blocker = tmp_path / "file"
    blocker.write_text("")
    monkeypatch.setattr(common, "WORKDIR", str(blocker / "sub"))       # cannot create a dir under a file
    audit.append("ticket", summary="x")


def test_format_is_readable():
    t = audit.format_event({"event": "ticket", "at_ny": "2026-10-28 08:50", "summary": "XAUUSD SHORT 3.41 lots",
                            "rationale": "because"})
    assert "TICKET: XAUUSD SHORT 3.41 lots" in t and "because" in t
    o = audit.format_event({"event": "outcome", "at_ny": "t", "outcome": "ORDER_PLACED", "reasons": [],
                            "order": {"ticket": 7, "price": 4052.28}})
    assert "ORDER_PLACED" in o and "7" in o and "4052.28" in o
    assert "not approved" in audit.format_event({"event": "decision", "approved": False})


def test_ticket_decision_and_order_survive_a_closed_terminal(scenario):
    _, deps, _ = scenario
    asyncio.run(attempt(deps, SimpleNamespace(auto_approve=True), False))
    events = audit.read()
    assert [e["event"] for e in events] == ["ticket", "decision", "outcome"]
    ticket, decision, outcome = events
    assert ticket["plan"]["lots"] > 0 and ticket["summary"].startswith("XAUUSD")
    assert decision["approved"] is True and decision["ticket_hash"] == ticket["ticket_hash"]
    assert outcome["outcome"] == "ORDER_PLACED" and outcome["order"]["ticket"] == 5001


def test_rejected_ticket_is_logged_too(scenario, monkeypatch):
    _, deps, _ = scenario
    monkeypatch.setattr("builtins.input", lambda prompt="": "no")
    asyncio.run(attempt(deps, SimpleNamespace(auto_approve=False), False))
    events = audit.read()
    assert events[1]["approved"] is False and events[2]["outcome"] == "REJECTED"


def test_no_signal_outcome_is_logged(scenario):
    _, deps, now = scenario
    deps.clock = lambda: now.replace(hour=8, minute=40)
    deps.broker.as_of = now.replace(hour=8, minute=40)
    asyncio.run(attempt(deps, SimpleNamespace(auto_approve=False), False))
    assert [e["event"] for e in audit.read()] == ["outcome"] and audit.read()[0]["outcome"] == "WAITING"
