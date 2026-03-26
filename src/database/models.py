from datetime import datetime
from sqlalchemy import Column, Integer, Float, String, DateTime, Index
from sqlalchemy.orm import declarative_base
Base = declarative_base()

class OIHistory(Base):
    __tablename__ = 'oi_history'
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(32), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    oi_usd = Column(Float, nullable=False)
    price = Column(Float, nullable=False)
    volume_24h = Column(Float, nullable=True)
    __table_args__ = (Index('ix_oi_history_symbol_timestamp', 'symbol', 'timestamp'),)

    def __repr__(self):
        return f'<OIHistory(symbol={self.symbol}, ts={self.timestamp}, oi=${self.oi_usd:,.0f})>'

class SignalHistory(Base):
    __tablename__ = 'signal_history'
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(32), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)
    direction = Column(String(10), nullable=False)
    score = Column(Float, nullable=False)
    confidence = Column(Float, nullable=False)
    entry_price = Column(Float, nullable=False)
    stop_loss = Column(Float, nullable=True)
    target_1 = Column(Float, nullable=True)
    target_2 = Column(Float, nullable=True)
    target_3 = Column(Float, nullable=True)
    oi_usd = Column(Float, nullable=True)
    oi_mc_ratio = Column(Float, nullable=True)
    funding_rate = Column(Float, nullable=True)
    aggression_2h = Column(Float, nullable=True)
    exit_price = Column(Float, nullable=True)
    exit_timestamp = Column(DateTime, nullable=True)
    pnl_percent = Column(Float, nullable=True)
    result = Column(String(20), nullable=True)
    __table_args__ = (Index('ix_signal_history_symbol_timestamp', 'symbol', 'timestamp'),)

    def __repr__(self):
        return f'<Signal({self.direction} {self.symbol} score={self.score:.1f})>'