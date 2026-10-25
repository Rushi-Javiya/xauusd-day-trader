"""Thin launcher so `python scripts/fetch.py` keeps working without installing the package."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from xauusd_trader.fetch import main  # noqa: E402

if __name__ == "__main__":
    main()
