import datetime as dt

import pytest

from xauusd_trader.agent import guard
from xauusd_trader.common import iso
from xauusd_trader.risk import make_verdict

D = dt.datetime
NOW = D(2026, 1, 12, 9, 0)


@pytest.fixture
def plan():
    return {"symbol": "XAUUSD", "side": "long", "setup": "orb", "entry": 3350.0, "stop": 3345.0, "tp": 3361.05,
            "target_r": 2.0, "risk_per_oz": 5.35, "spread_used": 0.35, "lots": 0.09, "risk_acct": 48.15,
            "max_loss_allowed": 50.0, "rr": 2.0}


def approved(plan):
    return {"approved": True, "ticket_hash": guard.ticket_hash(plan)}


def test_account_must_be_demo():
    assert guard.check_account({"trade_mode": 0}) == []
    assert guard.check_account({"trade_mode": 2})
    assert guard.check_account({})


def test_missing_contract_size_blocks_until_confirmed(cfg):
    assert guard.check_symbol({"trade_contract_size": None}, cfg)
    cfg["contract_size_confirmed"] = True
    assert guard.check_symbol({"trade_contract_size": None}, cfg) == []


def test_contract_size_mismatch_blocks(cfg):
    assert guard.check_symbol({"trade_contract_size": 1000.0}, cfg)
    assert guard.check_symbol({"trade_contract_size": 100.0}, cfg) == []


def test_lot_rules_mismatch_blocks(cfg):
    assert guard.check_symbol({"trade_contract_size": 100, "volume_min": 0.1}, cfg)
    assert guard.check_symbol({"trade_contract_size": 100, "volume_step": 0.1}, cfg)


@pytest.mark.parametrize("flags,expected", [(2, 1), (3, 1), (1, 0), (0, 2), (None, 2)])
def test_filling_type_from_symbol_flags(flags, expected):
    assert guard.filling_type({"filling_mode": flags}) == expected


def test_detect_time_mode(cfg):
    utc = D(2026, 1, 12, 14, 0)                           # winter: broker = UTC+2
    assert guard.detect_time_mode("2026-01-12T16:00:05+00:00", utc, cfg)[0] == "server"
    assert guard.detect_time_mode("2026-01-12T14:00:05Z", utc, cfg)[0] == "utc"
    assert guard.detect_time_mode("2026-01-12T19:00:00", utc, cfg)[0] == "mismatch"
    summer = D(2026, 7, 1, 14, 0)                         # summer: broker = UTC+3
    assert guard.detect_time_mode("2026-07-01T17:00:00", summer, cfg)[0] == "server"


def test_drift_limit(cfg, plan):
    ok = {"ask": 3350.35 + 1.0, "bid": 3351.0}
    far = {"ask": 3350.35 + 3.0, "bid": 3353.0}           # limit = 0.5 * 5.35 = 2.675
    assert guard.check_drift(plan, ok, cfg) == []
    assert guard.check_drift(plan, far, cfg)


def test_drift_uses_bid_for_shorts(cfg, plan):
    plan.update(side="short", entry=3350.0, stop=3355.0, risk_per_oz=5.0, spread_used=0.35)
    assert guard.check_drift(plan, {"bid": 3349.0, "ask": 3349.35}, cfg) == []
    assert guard.check_drift(plan, {"bid": 3346.0, "ask": 3346.35}, cfg)


def test_build_request_matches_plan_exactly(cfg, plan):
    tick = {"bid": 3350.1, "ask": 3350.38}
    r = guard.build_request(plan, tick, {"filling_mode": 2}, cfg)
    assert r["action"] == 1 and r["type"] == 0 and r["price"] == 3350.38
    assert (r["volume"], r["sl"], r["tp"], r["symbol"]) == (0.09, 3345.0, 3361.05, "XAUUSD")
    assert r["type_filling"] == 1 and r["magic"] == 777001 and len(r["comment"]) <= 31
    plan.update(side="short")
    r = guard.build_request(plan, tick, {"filling_mode": 2}, cfg)
    assert r["type"] == 1 and r["price"] == 3350.1


def test_authorize_happy_path(cfg, plan):
    v = make_verdict(plan, cfg, NOW, [])
    assert guard.authorize(plan, v, approved(plan), NOW + dt.timedelta(minutes=2), cfg) == []


def test_authorize_needs_pass_verdict(cfg, plan):
    v = make_verdict(plan, cfg, NOW, ["news blackout"])
    assert guard.authorize(plan, v, approved(plan), NOW, cfg)
    assert guard.authorize(plan, None, approved(plan), NOW, cfg)


def test_authorize_rejects_verdict_for_other_plan(cfg, plan):
    v = make_verdict(plan, cfg, NOW, [])
    changed = dict(plan, lots=0.5)
    out = guard.authorize(changed, v, approved(changed), NOW, cfg)
    assert any("different plan" in x for x in out)


def test_authorize_rejects_expired_verdict(cfg, plan):
    v = make_verdict(plan, cfg, NOW, [])
    out = guard.authorize(plan, v, approved(plan), NOW + dt.timedelta(minutes=11), cfg)
    assert any("expired" in x for x in out)


@pytest.mark.parametrize("approval", [None, {}, {"approved": False}, {"approved": "yes"},
                                      {"approved": True, "ticket_hash": "nope"}, {"approved": True}])
def test_authorize_needs_exact_explicit_approval(cfg, plan, approval):
    v = make_verdict(plan, cfg, NOW, [])
    assert guard.authorize(plan, v, approval, NOW, cfg)


def test_authorize_without_plan(cfg):
    assert guard.authorize(None, None, None, NOW, cfg) == ["no plan"]
    assert iso(NOW)
