"""
backend/models/btc_price.py

One BTC/USD price per UTC day: the local price history every historical
valuation reads (backend/services/price_history.py). Created by migration
0004.
"""

from sqlalchemy import Column, Date, Numeric, String

from backend.database import Base


class BtcPriceDaily(Base):
    __tablename__ = "btc_price_daily"

    day = Column(Date, primary_key=True, doc="UTC calendar day")
    usd = Column(Numeric(18, 2), nullable=False, doc="The day's price at 00:00 UTC (daily open)")
    source = Column(String, nullable=False, doc="Where it came from, e.g. 'bitstamp'")
