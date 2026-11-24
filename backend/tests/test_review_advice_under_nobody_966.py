"""
#966: Ledger Review's advice for a value left blank or $0 said to clear it
"to use that hour's price". When BitcoinTX asks no one for prices (the price
source Nobody, none chosen yet, one not confirmed, or a server's invalid
settings), clearing fills nothing unless the hour's price is already stored,
and the item stays listed. The advice then says to type the value, and why,
as the Edit form says it.
"""

import pytest

from backend.services import outbound, review

ADVISED = ("income_without_value", "gift_without_value", "zero_proceeds_spend", "income_value_off")


def _actions(monkeypatch, **settings) -> dict[str, str]:
    monkeypatch.setattr(outbound, "current", lambda: outbound.NetworkSettings(**settings))
    return {key: review.advice(key) for key in ADVISED}


@pytest.mark.parametrize("settings, why", [
    ({"price_source": "off"}, "you chose Nobody"),
    ({"price_source": "unset"}, "no price source is chosen yet (choose one on the Dashboard)"),
    ({"price_source": "public", "waiting": True}, "the price source isn't confirmed yet (confirm it on the Dashboard)"),
    ({"price_source": "public", "invalid": True}, "this server's price settings aren't valid"),
])
def test_when_nothing_is_asked_the_advice_says_to_type_the_value_and_why(monkeypatch, settings, why):
    for key, action in _actions(monkeypatch, **settings).items():
        assert "only if BitcoinTX already has that hour's price" in action, (key, action)
        assert action.endswith(f"since {why}."), (key, action)
        assert "to use that hour's price" not in action, (key, action)


def test_when_prices_are_asked_the_advice_is_as_before(monkeypatch):
    actions = _actions(monkeypatch, price_source="public")
    assert actions["gift_without_value"] == (
        "Edit each one: clear its FMV (USD) to use that hour's price, or type its value when it left.")
    assert actions["income_without_value"] == review.CHECKS["income_without_value"][1]


def test_the_review_carries_the_advice(monkeypatch, auth_client, test_engine):
    """build_review gives each check its advice for the price choice in use."""
    from sqlalchemy.orm import Session
    monkeypatch.setattr(outbound, "current", lambda: outbound.NetworkSettings(price_source="off"))
    with Session(test_engine) as db:
        checks = {c["key"]: c for c in review.build_review(db)["checks"]}
    assert checks["gift_without_value"]["action"].endswith("since you chose Nobody.")
