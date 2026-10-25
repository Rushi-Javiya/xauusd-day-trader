"""Thin launcher so `python scripts/levels.py` keeps working without installing the package."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from xauusd_trader.levels import main  # noqa: E402

if __name__ == "__main__":
    main()
