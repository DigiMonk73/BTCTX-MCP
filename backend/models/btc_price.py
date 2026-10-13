"""
The local BTC/USD price history: one price per UTC day (btc_price_daily,
backend/services/price_history.py, migration 0004) and one per UTC hour
(btc_price_hourly, backend/services/hourly_prices.py, migration 0009).
"""

from sqlalchemy import Column, Date, Integer, Numeric, String

from backend.database import Base


class BtcPriceDaily(Base):
    __tablename__ = "btc_price_daily"

    day = Column(Date, primary_key=True, doc="UTC calendar day")
    usd = Column(Numeric(18, 2), nullable=False, doc="The day's price at 00:00 UTC (daily open)")
    source = Column(String, nullable=False, doc="Where it came from, e.g. 'bitstamp'")


class BtcPriceHourly(Base):
    """An hour this install priced from its source (the year files' hours
    aren't copied here). A stored hour never changes."""
    __tablename__ = "btc_price_hourly"

    hour = Column(Integer, primary_key=True, autoincrement=False, doc="The UTC hour's start, Unix seconds")
    usd = Column(Numeric(18, 2), nullable=False, doc="The hour's opening price")
    source = Column(String, nullable=False, doc="Where it came from, e.g. 'bitstamp' or 'mempool'")
