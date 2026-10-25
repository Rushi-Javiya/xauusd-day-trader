import datetime as dt

import pytest

from xauusd_trader import common
from xauusd_trader.common import (atr, day_key, hhmm, load_bars, ny_to_utc, parse_time, server_to_utc, to_ny, us_dst)

D = dt.datetime


def test_us_dst_boundaries_2026():
    assert not us_dst(D(2026, 3, 8, 6, 59))
    assert us_dst(D(2026, 3, 8, 7, 0))
    assert us_dst(D(2026, 11, 1, 5, 59))
    assert not us_dst(D(2026, 11, 1, 6, 0))


def test_to_ny_summer_and_winter():
    assert to_ny(D(2026, 7, 1, 12, 0)) == D(2026, 7, 1, 8, 0)
    assert to_ny(D(2026, 1, 15, 12, 0)) == D(2026, 1, 15, 7, 0)


@pytest.mark.parametrize("ny", [D(2026, 7, 1, 8, 30), D(2026, 1, 15, 8, 30), D(2026, 12, 1, 17, 0)])
def test_ny_utc_roundtrip(ny):
    assert to_ny(ny_to_utc(ny)) == ny


def test_server_to_utc_uses_summer_and_winter_offsets(cfg):
    assert server_to_utc(D(2026, 7, 1, 15, 0), cfg) == D(2026, 7, 1, 12, 0)
    assert server_to_utc(D(2026, 1, 15, 14, 0), cfg) == D(2026, 1, 15, 12, 0)


def test_hhmm():
    assert hhmm("08:30") == 510
    assert hhmm("16:30") == 990


def test_day_key_rolls_at_1700_ny():
    assert day_key(D(2026, 1, 12, 16, 59)) == dt.date(2026, 1, 12)
    assert day_key(D(2026, 1, 12, 17, 0)) == dt.date(2026, 1, 13)


def test_parse_time_formats():
    assert parse_time(0) == D(1970, 1, 1)
    assert parse_time("1768000000") == D(1970, 1, 1) + dt.timedelta(seconds=1768000000)
    assert parse_time("2026.01.12 08:30") == D(2026, 1, 12, 8, 30)
    assert parse_time("2026-01-12 08:30:00") == D(2026, 1, 12, 8, 30)
    with pytest.raises(ValueError):
        parse_time("not a time")


def test_atr_simple():
    bars = [
        {"h": 10, "l": 9, "c": 9.5},
        {"h": 11, "l": 9.5, "c": 10.5},   # TR 1.5
        {"h": 12, "l": 10.5, "c": 11.5},  # TR 1.5
    ]
    assert atr(bars) == pytest.approx(1.5)
    assert atr(bars[:1]) is None


def test_load_bars_mt5_tab_csv_converts_server_time_to_ny(tmp_path, cfg):
    f = tmp_path / "x.csv"
    f.write_text(
        "<DATE>\t<TIME>\t<OPEN>\t<HIGH>\t<LOW>\t<CLOSE>\n"
        "2026.01.12\t15:35:00\t2\t3\t1\t2.5\n"
        "2026.01.12\t15:30:00\t1\t2\t0.5\t1.5\n"
    )
    bars = load_bars(str(f), cfg)
    assert [b["t"] for b in bars] == [D(2026, 1, 12, 8, 30), D(2026, 1, 12, 8, 35)]
    assert bars[0]["o"] == 1.0 and bars[1]["c"] == 2.5


def test_load_bars_json_list(tmp_path, cfg):
    import json
    f = tmp_path / "x.json"
    f.write_text(json.dumps([{"time": "2026.01.12 15:30", "open": 1, "high": 2, "low": 0, "close": 1}]))
    assert load_bars(str(f), cfg)[0]["t"] == D(2026, 1, 12, 8, 30)


def test_load_config_overrides_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "WORKDIR", str(tmp_path))
    (tmp_path / "config.json").write_text('{"account_balance": 1234}')
    c = common.load_config()
    assert c["account_balance"] == 1234
    assert c["symbol"] == "XAUUSD"
