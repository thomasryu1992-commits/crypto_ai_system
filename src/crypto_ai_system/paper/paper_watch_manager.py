from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List

from crypto_ai_system.storage.latest import read_latest, write_latest


@dataclass
class PaperPosition:
    symbol: str
    side: str
    entry: float
    stop: float
    tp1: float
    tp2: float
    qty: float
    status: str = 'OPEN'

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PaperWatchManager:
    def __init__(self, state_path):
        self.state_path = state_path

    def load_positions(self) -> List[Dict[str, Any]]:
        payload = read_latest(self.state_path)
        return list(payload.get('positions', []))

    def add_candidate(self, trade_plan: Dict[str, Any]) -> Dict[str, Any]:
        positions = self.load_positions()
        pos = PaperPosition(
            symbol=trade_plan['symbol'], side=trade_plan['side'], entry=float(trade_plan['entry_reference']),
            stop=float(trade_plan['initial_stop']), tp1=float(trade_plan['tp1']), tp2=float(trade_plan['tp2']),
            qty=float(trade_plan['qty'])
        ).to_dict()
        positions.append(pos)
        write_latest(self.state_path, {'positions': positions})
        return pos
