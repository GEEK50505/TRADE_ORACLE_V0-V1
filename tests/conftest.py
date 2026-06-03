from __future__ import annotations

import sys
from pathlib import Path

# Ensure imports like `from config import settings` resolve during pytest collection.
# The `config/` package lives under the repository's `TRADE_ORACLE/` directory.
REPO_PACKAGE_ROOT = Path(__file__).resolve().parents[1]  # .../TRADE_ORACLE
if str(REPO_PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_PACKAGE_ROOT))
