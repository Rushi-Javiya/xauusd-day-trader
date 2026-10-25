import json

import pytest

from xauusd_trader import common
from xauusd_trader.common import DEFAULTS


@pytest.fixture
def cfg():
    return dict(DEFAULTS)


@pytest.fixture
def rows(tmp_path, monkeypatch):
    """150 days of synthetic M5 rows; WORKDIR points at a temp dir so journals never touch real data."""
    from xauusd_trader import make_demo_data
    monkeypatch.setattr(common, "WORKDIR", str(tmp_path))
    out = tmp_path / "M5.json"
    make_demo_data.main(150, str(out))
    return json.loads(out.read_text())


@pytest.fixture
def scenario(rows, cfg):
    """(paper broker, graph deps, now) positioned on a bar where a valid ORB signal just fired."""
    pytest.importorskip("langgraph")
    from helpers import find_signal_time
    from xauusd_trader.agent.broker import PaperBroker
    from xauusd_trader.agent.graph import Deps
    cfg["contract_size_confirmed"] = True
    now = find_signal_time(rows, cfg)
    broker = PaperBroker(rows, cfg, as_of_ny=now)
    deps = Deps(broker=broker, cfg=cfg, clock=lambda: now, news_loader=lambda: [], setups=("orb",))
    return broker, deps, now
