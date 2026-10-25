import datetime as dt

import pytest

from xauusd_trader import risk

D = dt.datetime
NOW = D(2026, 1, 12, 9, 0)  # Monday, inside the entry window


@pytest.fixture
def plan():
    return {"risk_acct": 48.0, "max_loss_allowed": 50.0, "rr": 2.0, "stop": 3345.0}


def row(**kw):
    r = {"date_ny": "2026-01-12", "exit": "", "pnl_acct": "", "risk_acct": "48", "r_multiple": ""}
    r.update(kw)
    return r


def test_pass_when_clean(cfg, plan):
    assert risk.evaluate(plan, cfg, NOW, [], []) == []


def test_blocks_outside_entry_window(cfg, plan):
    assert any("entry window" in w for w in risk.evaluate(plan, cfg, D(2026, 1, 12, 12, 0), [], []))
    assert any("entry window" in w for w in risk.evaluate(plan, cfg, D(2026, 1, 12, 8, 40), [], []))


@pytest.mark.parametrize("n", [D(2026, 1, 10, 9, 0), D(2026, 1, 11, 12, 0), D(2026, 1, 9, 17, 30)])
def test_blocks_when_market_closed(cfg, plan, n):
    assert any("market closed" in w for w in risk.evaluate(plan, cfg, n, [], []))


def test_blocks_oversized_risk(cfg, plan):
    plan["risk_acct"] = 60.0
    assert any("exceeds max loss" in w for w in risk.evaluate(plan, cfg, NOW, [], []))


def test_blocks_low_reward_to_risk(cfg, plan):
    plan["rr"] = 0.5
    assert any("reward:risk" in w for w in risk.evaluate(plan, cfg, NOW, [], []))


def test_blocks_max_trades(cfg, plan):
    rows = [row(exit="1", pnl_acct="5", r_multiple="0.1") for _ in range(3)]
    assert any("trades today" in w for w in risk.evaluate(plan, cfg, NOW, rows, []))


def test_yesterdays_trades_do_not_count(cfg, plan):
    rows = [row(date_ny="2026-01-09", exit="1", pnl_acct="-50", r_multiple="-1") for _ in range(5)]
    assert risk.evaluate(plan, cfg, NOW, rows, []) == []


def test_blocks_on_daily_loss_limit_worst_case(cfg, plan):
    rows = [row(exit="1", pnl_acct="-90", r_multiple="-1")]
    assert any("daily loss limit" in w for w in risk.evaluate(plan, cfg, NOW, rows, []))


def test_open_risk_counts_against_daily_limit(cfg, plan):
    rows = [row(risk_acct="60")]  # open trade, nothing closed
    assert any("daily loss limit" in w for w in risk.evaluate(plan, cfg, NOW, rows, []))


def test_blocks_after_consecutive_losses(cfg, plan):
    rows = [row(exit="1", pnl_acct="-10", r_multiple="-1"), row(exit="1", pnl_acct="-10", r_multiple="-1")]
    assert any("in a row" in w for w in risk.evaluate(plan, cfg, NOW, rows, []))


def test_win_between_losses_resets_streak(cfg, plan):
    rows = [row(exit="1", pnl_acct="-10", r_multiple="-1"), row(exit="1", pnl_acct="20", r_multiple="2")]
    assert not any("in a row" in w for w in risk.evaluate(plan, cfg, NOW, rows, []))


def test_news_blackout_window(cfg, plan):
    news = [{"time_ny": "2026-01-12 09:05", "title": "CPI"}]
    assert any("news blackout" in w for w in risk.evaluate(plan, cfg, NOW, [], news))
    assert not any("news blackout" in w for w in risk.evaluate(plan, cfg, D(2026, 1, 12, 9, 30), [], news))


def test_plan_hash_changes_with_plan(plan):
    h1 = risk.plan_hash(plan)
    plan["stop"] = 3344.0
    assert risk.plan_hash(plan) != h1
    assert len(h1) == 16
