from __future__ import annotations

import sys
from pathlib import Path

# Make `from config import settings` work during pytest collection.
# The `config/` package lives at <repo>/TRADE_ORACLE/config.
REPO_PACKAGE_ROOT = Path(__file__).resolve().parent  # .../TRADE_ORACLE
if str(REPO_PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_PACKAGE_ROOT))
