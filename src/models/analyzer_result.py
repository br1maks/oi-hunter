from typing import Optional, Literal
from pydantic import BaseModel, Field

class AnalyzerResult(BaseModel):
    analyzer_name: str = Field(..., description='Название анализатора')
    long_score: float = Field(..., ge=0, le=10, description='Score for LONG (0-10)')
    short_score: float = Field(..., ge=0, le=10, description='Score for SHORT (0-10)')
    confidence: float = Field(1.0, ge=0, le=1, description='Confidence level (0-1)')
    reasoning: str = Field(..., description='Explanation of the score')
    blocks_long: bool = Field(default=False, description='Блокирует LONG сигнал (критические условия для лонга)')
    blocks_short: bool = Field(default=False, description='Блокирует SHORT сигнал (критические условия для шорта)')
    alert_level: Literal['info', 'warning', 'critical'] = Field(default='info', description='Уровень критичности для логов и уведомлений')
    key_value: Optional[float] = Field(None, description='Key metric value (e.g., OI/MC ratio)')
    key_label: Optional[str] = Field(None, description='Label for key value')

    class Config:
        json_schema_extra = {'examples': [{'analyzer_name': 'OI/MC Analyzer', 'long_score': 9.0, 'short_score': 2.0, 'confidence': 0.95, 'reasoning': 'OI/MC ratio 0.28 in optimal zone (0.16-0.30) for longs', 'key_value': 0.28, 'key_label': 'OI/MC Ratio', 'blocks_long': False, 'blocks_short': False, 'alert_level': 'info'}, {'analyzer_name': 'OI/MC Analyzer', 'long_score': 0.0, 'short_score': 10.0, 'confidence': 1.0, 'reasoning': 'OI/MC ratio 0.85 in EXTREME danger zone (>0.70) - perfect for SHORT!', 'key_value': 0.85, 'key_label': 'OI/MC Ratio', 'blocks_long': True, 'blocks_short': False, 'alert_level': 'critical'}, {'analyzer_name': 'OI/MC Analyzer', 'long_score': 3.0, 'short_score': 2.0, 'confidence': 0.85, 'reasoning': 'OI/MC ratio 0.55 in HIGH RISK zone (0.51-0.70) - avoid longs', 'key_value': 0.55, 'key_label': 'OI/MC Ratio', 'blocks_long': True, 'blocks_short': False, 'alert_level': 'warning'}, {'analyzer_name': 'Already Pumped Analyzer', 'long_score': 0.0, 'short_score': 7.0, 'confidence': 0.9, 'reasoning': 'Price pumped +68% in 4h - high risk of dump', 'key_value': 68.0, 'key_label': 'Price Change 4H %', 'blocks_long': True, 'blocks_short': False, 'alert_level': 'warning'}]}