import pytest

from xauusd_trader.common import DEFAULTS


@pytest.fixture
def cfg():
    return dict(DEFAULTS)
