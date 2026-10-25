import pytest

from common import DEFAULTS


@pytest.fixture
def cfg():
    return dict(DEFAULTS)
