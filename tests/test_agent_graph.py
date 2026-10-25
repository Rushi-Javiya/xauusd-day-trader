import asyncio
import datetime as dt
import json

import pytest

pytest.importorskip("langgraph")

from langgraph.types import Command  # noqa: E402

from xauusd_trader import common, journal, levels, make_demo_data, strategy  # noqa: E402
from xauusd_trader import plan as planmod  # noqa: E402
from xauusd_trader.agent import guard  # noqa: E402
from xauusd_trader.agent.broker import BrokerError, PaperBroker  # noqa: E402
from xauusd_trader.agent.graph import Deps, build_graph  # noqa: E402
from xauusd_trader.common import bars_from_rows, group_days, parse_iso  # noqa: E402

THREAD = {"configurable": {"thread_id": "t1"}}


@pytest.fixture
def rows(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "WORKDIR", str(tmp_path))
    out = tmp_path / "M5.json"
    make_demo_data.main(150, str(out))
    return json.loads(out.read_text())


def find_signal_time(rows, cfg):
    """A deterministic day/time where the ORB setup fires early and yields a sizable plan."""
    by_day = group_days(bars_from_rows(rows, cfg))
    for date in sorted(by_day)[20:]:
        if date.weekday() > 4 or len(by_day[date]) < 100:
            continue
        lv = levels.compute(by_day, date, cfg)
        for s in strategy.find_signals(by_day[date], lv, cfg, ("orb",)):
            p, err = planmod.price_plan(s, cfg)
            if err or planmod.size_plan(p, cfg)[0] is None:
                continue
            t = parse_iso(s["time"])
            if t.hour < 11:
                return t
    raise AssertionError("no usable signal in synthetic data")


@pytest.fixture
def scenario(rows, cfg):
    cfg["contract_size_confirmed"] = True
    now = find_signal_time(rows, cfg)
    broker = PaperBroker(rows, cfg, as_of_ny=now)
    deps = Deps(broker=broker, cfg=cfg, clock=lambda: now, news_loader=lambda: [], setups=("orb",))
    return broker, deps, now


def invoke(graph, payload):
    return asyncio.run(graph.ainvoke(payload, THREAD))


def start(graph):
    return invoke(graph, {"log": []})


def test_stops_at_approval_and_sends_nothing(scenario):
    broker, deps, _ = scenario
    res = start(build_graph(deps))
    assert "__interrupt__" in res
    ticket = res["__interrupt__"][0].value
    assert ticket["ticket_hash"] == guard.ticket_hash(res["plan"])
    assert "lots" in ticket["summary"] and broker.sent == [] and broker.checked == []
    assert res["verdict"]["verdict"] == "PASS"


def test_approved_ticket_places_one_exact_order_and_journals_it(scenario):
    broker, deps, now = scenario
    g = build_graph(deps)
    res = start(g)
    h = res["__interrupt__"][0].value["ticket_hash"]
    res = invoke(g, Command(resume={"approved": True, "ticket_hash": h}))
    assert res["outcome"] == "ORDER_PLACED"
    assert len(broker.checked) == 1 and len(broker.sent) == 1
    req, plan = broker.sent[0], res["plan"]
    assert (req["volume"], req["sl"], req["tp"]) == (plan["lots"], plan["stop"], plan["tp"])
    assert req["type_filling"] == 1
    rows_ = journal.read()
    assert len(rows_) == 1 and rows_[0]["ticket"] == "5001" and rows_[0]["date_ny"] == str(now.date())


def test_rejected_ticket_sends_nothing(scenario):
    broker, deps, _ = scenario
    g = build_graph(deps)
    start(g)
    res = invoke(g, Command(resume={"approved": False}))
    assert res["outcome"] == "REJECTED" and broker.sent == []


def test_approval_for_a_different_ticket_is_refused(scenario):
    broker, deps, _ = scenario
    g = build_graph(deps)
    start(g)
    res = invoke(g, Command(resume={"approved": True, "ticket_hash": "deadbeef"}))
    assert res["outcome"] == "NOT_AUTHORIZED" and broker.sent == []


def test_non_demo_account_never_reaches_orders(rows, cfg):
    cfg["contract_size_confirmed"] = True
    now = find_signal_time(rows, cfg)
    broker = PaperBroker(rows, cfg, as_of_ny=now, trade_mode=2)
    res = start(build_graph(Deps(broker=broker, cfg=cfg, clock=lambda: now, news_loader=lambda: [])))
    assert res["outcome"] == "PREFLIGHT_FAILED" and "demo" in res["reasons"][0]
    assert "bars" not in res and broker.sent == []


def test_unknown_contract_size_blocks_until_confirmed(rows, cfg):
    now = find_signal_time(rows, cfg)
    broker = PaperBroker(rows, cfg, as_of_ny=now, contract_size=None)
    deps = Deps(broker=broker, cfg=cfg, clock=lambda: now, news_loader=lambda: [], setups=("orb",))
    assert start(build_graph(deps))["outcome"] == "PREFLIGHT_FAILED"


def test_missing_news_file_blocks(scenario):
    _, deps, _ = scenario
    deps.news_loader = lambda: None
    assert start(build_graph(deps))["outcome"] == "NEWS_UNCHECKED"


def test_news_blackout_blocks_via_risk_gate(scenario):
    _, deps, now = scenario
    deps.news_loader = lambda: [{"time_ny": common.iso(now + dt.timedelta(minutes=3)), "title": "CPI"}]
    res = start(build_graph(deps))
    assert res["outcome"] == "BLOCKED" and any("news blackout" in r for r in res["reasons"])


def test_waits_before_opening_range_completes(rows, cfg):
    cfg["contract_size_confirmed"] = True
    now = find_signal_time(rows, cfg).replace(hour=8, minute=40)
    broker = PaperBroker(rows, cfg, as_of_ny=now)
    res = start(build_graph(Deps(broker=broker, cfg=cfg, clock=lambda: now, news_loader=lambda: [])))
    assert res["outcome"] == "WAITING"


def test_price_move_after_approval_aborts(scenario):
    broker, deps, _ = scenario
    g = build_graph(deps)
    res = start(g)
    tick = asyncio.run(broker.tick("XAUUSD"))

    async def moved(symbol):
        return {**tick, "ask": tick["ask"] + 50, "bid": tick["bid"] + 50}

    broker.tick = moved
    h = res["__interrupt__"][0].value["ticket_hash"]
    res = invoke(g, Command(resume={"approved": True, "ticket_hash": h}))
    assert res["outcome"] == "PRICE_MOVED" and broker.sent == []


def test_failed_order_check_stops_before_send(scenario):
    broker, deps, _ = scenario
    g = build_graph(deps)
    res = start(g)

    async def bad_check(request):
        return {"retcode": 10030, "comment": "Unsupported filling mode"}

    broker.order_check = bad_check
    h = res["__interrupt__"][0].value["ticket_hash"]
    res = invoke(g, Command(resume={"approved": True, "ticket_hash": h}))
    assert res["outcome"] == "ORDER_CHECK_FAILED" and broker.sent == []


def test_broker_error_on_send_is_reported_not_journaled(scenario):
    broker, deps, _ = scenario
    g = build_graph(deps)
    res = start(g)

    async def boom(request):
        raise BrokerError("Invalid stops")

    broker.order_send = boom
    h = res["__interrupt__"][0].value["ticket_hash"]
    res = invoke(g, Command(resume={"approved": True, "ticket_hash": h}))
    assert res["outcome"] == "ORDER_FAILED" and journal.read() == []
