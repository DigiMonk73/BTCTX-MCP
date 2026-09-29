"""
Portfolio figures for the dashboard: balances, average cost, gains and
income (services/calculation.py), as JSON numbers.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from decimal import Decimal

from backend.services.calculation import (
    get_account_balance,
    get_all_account_balances,
    get_gains_and_losses,
    get_average_cost_basis
)
from backend.database import get_db

router = APIRouter(tags=["calculations"])


@router.get("/account/{account_id}/balance")
def api_get_account_balance(account_id: int, db: Session = Depends(get_db)) -> dict:
    """One account's balance: {"account_id", "balance"}."""
    balance = get_account_balance(db, account_id)
    return {"account_id": account_id, "balance": float(balance)}


@router.get("/accounts/balances")
def api_get_all_account_balances(db: Session = Depends(get_db)) -> list[dict]:
    """Every account's balance: [{"account_id", "name", "currency", "balance"}]."""
    results = get_all_account_balances(db)
    for item in results:
        item["balance"] = float(item["balance"])
    return results


@router.get("/average-cost-basis")
def api_get_average_cost_basis(db: Session = Depends(get_db)) -> dict:
    """The average USD cost of the BTC still held: {"averageCostBasis"}."""
    average_basis_decimal = get_average_cost_basis(db)
    average_basis = float(average_basis_decimal)

    return {"averageCostBasis": average_basis}


@router.get("/gains-and-losses")
def api_get_gains_and_losses(db: Session = Depends(get_db)) -> dict:
    """Realized gains and losses, income by source, proceeds and fees
    (services/calculation.get_gains_and_losses)."""
    calculations = get_gains_and_losses(db)

    def convert_decimal(item):
        if isinstance(item, Decimal):
            return float(item)
        if isinstance(item, dict):
            return {key: convert_decimal(value) for key, value in item.items()}
        if isinstance(item, list):
            return [convert_decimal(subitem) for subitem in item]
        return item

    return convert_decimal(calculations)
