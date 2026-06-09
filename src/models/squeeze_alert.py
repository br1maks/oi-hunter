from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class SqueezeAlert:
    symbol: str
    timestamp: datetime
    direction: str              # 'LONG_SQUEEZE' or 'SHORT_SQUEEZE'
    alert_level: str            # 'WATCH', 'STRONG', or 'TRIGGERED'
    squeeze_score: float        # 0–10 composite score

    # Component breakdown
    c1_score: Optional[float]   # Trapped positions (30%)
    c2_score: Optional[float]   # Liquidity vacuum (30%)
    c3_score: Optional[float]   # Aggression pressure (25%)
    c4_score: Optional[float]   # Coiling / over-extension (15%)
    funding_adj: float          # Funding rate adjustment applied

    # Market context
    price: float
    oi_usd: float
    oi_change_1h: Optional[float]
    price_change_1h: Optional[float]
    price_change_4h: Optional[float]
    ob_ratio: Optional[float]           # bid/ask (long) or ask/bid (short)
    aggression_5m: Optional[float]      # % buy volume in last 5m
    aggression_accel: Optional[float]   # delta vs 2h baseline
    funding_rate: float
    vci: Optional[float]
    cfc: int

    reasoning: str
