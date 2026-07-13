from __future__ import annotations

"""Compatibility bridge for the legacy data_collector_bot package.

The Step151E~157E roadmap uses the new src/crypto_ai_system Extended adapter as
the primary market-data path. Existing legacy modules can import this bridge
when they need an Extended-normalized snapshot without depending on Binance.
"""

import sys
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def collect_extended_snapshot() -> Dict[str, Any]:
    from crypto_ai_system.config import load_config
    from crypto_ai_system.data.collectors import collect_extended_market_data

    cfg = load_config(ROOT)
    return collect_extended_market_data(cfg)
