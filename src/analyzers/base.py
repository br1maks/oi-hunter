from abc import ABC, abstractmethod
from typing import Optional
from ..models.market_data import MarketData
from ..models.analyzer_result import AnalyzerResult

class BaseAnalyzer(ABC):

    def __init__(self, weight: float=1.0):
        self.weight = weight

    @property
    @abstractmethod
    def analyzer_name(self) -> str:
        pass

    @abstractmethod
    def analyze(self, data: MarketData) -> Optional[AnalyzerResult]:
        pass

    def _validate_data(self, data: MarketData) -> bool:
        if not data.symbol or data.price <= 0:
            return False
        return True

    def _calculate_confidence(self, data: MarketData) -> float:
        return 1.0

    def __repr__(self) -> str:
        return f'{self.analyzer_name} (weight={self.weight})'