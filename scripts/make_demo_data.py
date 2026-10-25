"""Thin launcher so `python scripts/make_demo_data.py` keeps working without installing the package."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from xauusd_trader.make_demo_data import main  # noqa: E402

if __name__ == "__main__":
    main(*(int(x) for x in sys.argv[1:2]))
