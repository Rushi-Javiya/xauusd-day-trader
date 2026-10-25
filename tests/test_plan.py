import pytest

from xauusd_trader import plan


def sig(side, entry=3350.0, **kw):
    s = {"side": side, "entry": entry, "setup": "orb", "atr5": 1.5, "or_high": 3350.0, "or_low": 3345.0,
         "stop_hint": 3345.0 if side == "long" else 3355.0, "time": "2026-01-12 08:50"}
    s.update(kw)
    return s


def test_long_plan_models_spread(cfg):
    p, err = plan.price_plan(sig("long"), cfg)
    assert err is None
    assert p["risk_per_oz"] == pytest.approx(5.35)       # entry at ask, stopped on bid
    assert p["tp"] == pytest.approx(3350.35 + 2 * 5.35, abs=0.01)


def test_short_plan(cfg):
    p, err = plan.price_plan(sig("short"), cfg)
    assert err is None
    assert p["risk_per_oz"] == pytest.approx(5.0)
    assert p["tp"] == pytest.approx(3340.0)


def test_refuses_stop_on_wrong_side(cfg):
    _, err = plan.price_plan(sig("long", stop_hint=3351.0), cfg)
    assert err.startswith("REFUSED")
    _, err = plan.price_plan(sig("short", stop_hint=3349.0), cfg)
    assert err.startswith("REFUSED")


def test_refuses_too_tight_stop(cfg):
    _, err = plan.price_plan(sig("long"), cfg, stop="dist:1.0")
    assert "too tight" in err


@pytest.mark.parametrize("mode,expected", [("dist:4", 3346.0), ("price:3340", 3340.0), ("atr:2", 3347.0)])
def test_stop_modes_long(cfg, mode, expected):
    p, err = plan.price_plan(sig("long"), cfg, stop=mode)
    assert err is None and p["stop"] == pytest.approx(expected)


def test_unknown_stop_mode(cfg):
    _, err = plan.price_plan(sig("long"), cfg, stop="banana")
    assert "unknown stop mode" in err


def test_size_rounds_lots_down_and_stays_within_max_loss(cfg):
    p, _ = plan.price_plan(sig("long"), cfg)
    out, err = plan.size_plan(p, cfg)
    assert err is None
    assert out["lots"] == pytest.approx(0.09)             # raw 0.0935
    assert out["risk_acct"] <= out["max_loss_allowed"]


def test_size_refuses_instead_of_bumping_to_min_lot(cfg):
    p, _ = plan.price_plan(sig("long"), cfg)
    out, err = plan.size_plan(p, cfg, balance=100)
    assert out is None and err.startswith("REFUSED")


def test_size_respects_volume_max(cfg):
    cfg["volume_max"] = 0.05
    p, _ = plan.price_plan(sig("long"), cfg)
    out, _ = plan.size_plan(p, cfg)
    assert out["lots"] == pytest.approx(0.05)


def test_eur_account_scales_risk(cfg):
    cfg["account_ccy_per_usd"] = 0.5
    p, _ = plan.price_plan(sig("short"), cfg)
    out, _ = plan.size_plan(p, cfg)
    assert out["lots"] == pytest.approx(0.2)              # 50 / (100 * 5 * 0.5)
