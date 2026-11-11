import os
import time

import pytest

pytest.importorskip("langgraph")

from xauusd_trader.agent import doctor  # noqa: E402


def levels_of(checks):
    return {msg: lvl for lvl, msg in checks}


def test_config_ok_when_terminal_exists_and_contract_confirmed(cfg, tmp_path):
    exe = tmp_path / "terminal64.exe"
    exe.write_text("")
    cfg.update(mt5_path=str(exe), contract_size_confirmed=True)
    checks = doctor.check_config(cfg)
    assert [lvl for lvl, _ in checks] == ["OK", "OK", "OK", "OK"]


def test_config_flags_missing_terminal_and_unconfirmed_contract(cfg):
    cfg.update(mt5_path="C:/nope/terminal64.exe", contract_size_confirmed=False)
    lv = [lvl for lvl, _ in doctor.check_config(cfg)]
    assert lv[0] == "FAIL" and lv[1] == "WARN"
    cfg["mt5_path"] = ""
    assert doctor.check_config(cfg)[0][0] == "FAIL"


def test_config_reports_which_limits_are_off(cfg):
    cfg.update(max_trades_per_day=0, entry_window=False)
    assert any("limits OFF: entry window, trades per day" in m for _, m in doctor.check_config(cfg))


def test_news_file_missing_recent_and_stale(tmp_path):
    f = tmp_path / "news.json"
    assert doctor.check_news_file(str(f))[0] == "WARN"
    f.write_text("[]")
    assert doctor.check_news_file(str(f))[0] == "OK"
    old = time.time() - 30 * 3600
    os.utime(f, (old, old))
    lvl, msg = doctor.check_news_file(str(f))
    assert lvl == "WARN" and "false all-clear" in msg


def test_api_key_missing_is_a_warning_not_a_crash(cfg, monkeypatch):
    import asyncio
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert asyncio.run(doctor.check_api_key(cfg))[0] == "WARN"


def test_render_marks_each_level():
    out = doctor.render([("OK", "a"), ("WARN", "b"), ("FAIL", "c")])
    assert out.splitlines() == ["[ OK ] a", "[WARN] b", "[FAIL] c"]
