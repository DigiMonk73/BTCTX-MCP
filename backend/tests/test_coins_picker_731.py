"""
The form's coin picker, its server side (#711, step C3, #731): the list of
the coins a transaction moves (#706) grows into what the picker needs. It
covers a bitcoin Withdrawal from a wallet as well as a Transfer, and for a
wallet it gives `held`: what the wallet holds when the transaction comes,
before it takes any, one line per acquisition, captured by the engine's
hook in the save's own path (C2a), so the picker, the list and the save
can't disagree. A choice its wallet doesn't hold that day still answers
with what's held, so the picker can show it; lots made before migration
0101 are replayed first; `dated_today` says when "Highest cost first" may
be offered (Q3). The past-year question gains one line when a write adds
or changes a choice dated in an earlier tax year (6.2).

The ledger is test_chosen_coins_711's: Wallet holds A1 (0.3 BTC for $300,
originally acquired 2017-03-01) and A2 (0.5 BTC for $45,000, 2025-01-15),
the price $50,000 at every hour.
"""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from backend.services import past_years
from backend.tests.test_chosen_coins_711 import (  # noqa: F401  (owner, chose_a2: fixtures)
    EXCHANGE_BTC, LEAVES, WALLET, buy, chose_a2, coins, deposit, forget_acquisitions, owner, saved, spend, transfer,
)

URL = "/api/transactions/coins-moved"
NOT_LISTED = "Only a Transfer, or a bitcoin Withdrawal from one of your wallets, lists the coins that leave."
CHOICE_LINE = "A choice of coins counts only if you made it by the time they left and your records show it."


def coin(acquired: str, btc: str, cost: str, acquired_txn_id: int, inherited: bool = False) -> dict:
    return {"acquired": acquired, "btc": btc, "cost_usd": cost, "inherited": inherited,
            "acquired_txn_id": acquired_txn_id}


def held(acquired_txn_id: int, acquired: str, btc: str, cost: str, term: str, oldest_first: str, *,
         source: str | None = "MyBTC", kind: str = "Deposit", acquired_in: str = "Wallet", dated: str | None = None,
         inherited: bool = False) -> dict:
    return {"acquired_txn_id": acquired_txn_id, "kind": kind, "source": source, "acquired_in": acquired_in,
            "date": dated or acquired, "acquired": acquired, "inherited": inherited, "btc": btc, "cost_usd": cost,
            "term": term, "oldest_first": oldest_first}


def wallet_then(ids, a1_btc="0.30000000", a1_cost="300.00", a1_first="0.10010000", a2_first="0.00000000"):
    """What Wallet holds on 2025-06-01 before anything leaves: A1 (long-term
    then) and A2 (short-term); oldest first would take from A1 first."""
    return [held(ids["A1"], "2017-03-01", a1_btc, a1_cost, "LONG", a1_first, dated="2023-01-10"),
            held(ids["A2"], "2025-01-15", "0.50000000", "45000.00", "SHORT", a2_first)]


def test_a_spend_from_a_wallet_lists_the_coins_that_leave_and_what_the_wallet_holds(owner):  # noqa: F811
    """Oldest first: the fee (0.0001) and the amount (0.1) come from A1, a
    piece of $100.00 (its running share after the fee's $0.10)."""
    ids = owner.ids
    r = owner.post(URL, json=spend(LEAVES, "0.1", "10000", "0.0001"))
    assert r.status_code == 200, r.text
    assert r.json() == {
        "coins": [coin("2017-03-01", "0.10000000", "100.00", ids["A1"])],
        "fee_btc": "0.00010000",
        "detail": None,
        "held": wallet_then(ids),
        "dated_today": False,
    }


def test_with_a_choice_the_coins_chosen_leave_and_the_wallet_holds_the_same(owner):  # noqa: F811
    ids = owner.ids
    r = owner.post(URL, json=spend(LEAVES, "0.1", "10000", "0.0001", coins((ids["A2"], "0.1001"))))
    assert r.status_code == 200, r.text
    assert r.json()["coins"] == [coin("2025-01-15", "0.10000000", "9000.00", ids["A2"])]
    assert r.json()["held"] == wallet_then(ids)  # before it takes any: the choice changes nothing there


def test_a_transfer_from_a_wallet_lists_its_coins_with_their_acquisition_and_the_wallet(owner):  # noqa: F811
    ids = owner.ids
    r = owner.post(URL, json=transfer(LEAVES, "0.4001", "0.0001"))
    assert r.status_code == 200, r.text
    assert r.json() == {
        "coins": [coin("2017-03-01", "0.29990000", "299.90", ids["A1"]),
                  coin("2025-01-15", "0.10010000", "9009.00", ids["A2"])],
        "fee_btc": "0.00010000",
        "detail": None,
        "held": wallet_then(ids, a1_first="0.30000000", a2_first="0.10010000"),
        "dated_today": False,
    }


def test_from_an_exchange_nothing_is_held_to_choose_from(owner):  # noqa: F811
    """An exchange's coins leave oldest first, as its Form 1099-DA reports them."""
    a4 = buy(owner, "2025-02-01T12:00:00Z", "1", "100000")
    r = owner.post(URL, json=transfer(LEAVES, "0.3", frm=EXCHANGE_BTC, to=WALLET))
    assert r.status_code == 200, r.text
    assert r.json()["coins"] == [coin("2025-02-01", "0.30000000", "30000.00", a4)]
    assert r.json()["held"] is None


def test_inherited_and_bought_coins_say_how_and_where_they_were_acquired(owner):  # noqa: F811
    a3 = deposit(owner, "2022-01-10T12:00:00Z", "0.01", "400", acquired="2021-12-01", source="Inherited")
    a4 = buy(owner, "2025-02-01T12:00:00Z", "1", "100000")
    saved(owner.post("/api/transactions", json=transfer("2025-02-10T12:00:00Z", "0.3", frm=EXCHANGE_BTC, to=WALLET)))
    r = owner.post(URL, json=spend(LEAVES, "0.1", "10000"))
    assert r.status_code == 200, r.text
    lines = {line["acquired_txn_id"]: line for line in r.json()["held"]}
    assert lines[a3] == held(a3, "2021-12-01", "0.01000000", "400.00", "LONG", "0.00000000", source="Inherited",
                             dated="2022-01-10", inherited=True)
    assert lines[a4] == held(a4, "2025-02-01", "0.30000000", "30000.00", "SHORT", "0.00000000", kind="Buy",
                             source=None, acquired_in="Exchange BTC")


def test_a_backdated_transfer_and_an_edit_hear_what_the_wallet_held_on_their_date(owner):  # noqa: F811
    """A spend on 2025-09-01 takes 0.25 of A1; a transfer dated before it,
    and an edit of one dated then, see all of A1, as their replay does."""
    ids = owner.ids
    saved(owner.post("/api/transactions", json=spend("2025-09-01T12:00:00Z", "0.25", "25000")))
    r = owner.post(URL, json=transfer(LEAVES, "0.1"))  # dated before it: the ledger is replayed
    assert r.status_code == 200, r.text
    assert r.json()["held"] == wallet_then(ids, a1_first="0.10000000")
    t = saved(owner.post("/api/transactions", json=transfer(LEAVES, "0.1")))
    r = owner.post(f"/api/transactions/{t}/coins-moved", json=transfer(LEAVES, "0.2"))
    assert r.status_code == 200, r.text
    assert r.json()["held"] == wallet_then(ids, a1_first="0.20000000")


@pytest.mark.parametrize("body", [
    spend("2025-01-01T12:00:00Z", "0.1", "10000"),  # dated before A2 arrived
])
def test_a_choice_its_wallet_doesnt_hold_then_answers_with_what_it_holds(owner, body):  # noqa: F811
    ids = owner.ids
    r = owner.post(URL, json={**body, "chosen_coins": coins((ids["A2"], "0.1"))})
    assert r.status_code == 200, r.text
    assert r.json() == {
        "coins": None,
        "fee_btc": None,
        "detail": (f"Wallet holds 0.00000000 BTC of the coins from transaction {ids['A2']} (a Deposit of "
                   "2025-01-15) on this date, not the 0.10000000 BTC chosen."),
        "held": [held(ids["A1"], "2017-03-01", "0.30000000", "300.00", "LONG", "0.10000000", dated="2023-01-10")],
        "dated_today": False,
    }


def test_an_edit_whose_stored_choice_isnt_held_on_its_new_date_answers_with_what_is(chose_a2):  # noqa: F811
    ids = chose_a2.ids
    r = chose_a2.post(f"/api/transactions/{ids['S']}/coins-moved", json={"timestamp": "2025-01-01T12:00:00Z"})
    assert r.status_code == 200, r.text
    assert r.json()["coins"] is None
    assert r.json()["detail"].startswith("Wallet holds 0.00000000 BTC of the coins from transaction")
    assert [line["acquired_txn_id"] for line in r.json()["held"]] == [ids["A1"]]


def test_a_choice_that_takes_another_transactions_chosen_coins_is_refused_as_its_save_is(chose_a2):  # noqa: F811
    """Taking coins a later transaction chose is the later one's refusal (Q2): the save's own words."""
    body = transfer("2025-03-01T12:00:00Z", "0.75")
    listed = chose_a2.post(URL, json=body)
    saved_ = chose_a2.post("/api/transactions", json=body)
    assert listed.status_code == saved_.status_code == 400
    assert listed.json()["detail"] == saved_.json()["detail"]


def test_lots_without_their_acquisition_are_replayed_first(owner):  # noqa: F811
    forget_acquisitions(owner)
    ids = owner.ids
    r = owner.post(URL, json=spend(LEAVES, "0.1", "10000", "0.0001", coins((ids["A2"], "0.1001"))))
    assert r.status_code == 200, r.text
    assert r.json()["held"] == wallet_then(ids)
    assert r.json()["coins"] == [coin("2025-01-15", "0.10000000", "9000.00", ids["A2"])]


def test_past_the_time_budget_nothing_is_listed_and_it_says_so(owner, monkeypatch):  # noqa: F811
    monkeypatch.setattr(past_years, "DRY_RUN_SECONDS", 0)
    r = owner.post(URL, json=spend("2024-01-01T12:00:00Z", "0.1", "10000"))  # backdated: replayed
    assert r.status_code == 200, r.text
    assert r.json() == {"coins": None, "fee_btc": None, "held": None, "dated_today": False,
                        "detail": "BitcoinTX couldn't work out in time which coins move. Saving isn't affected."}


def now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def test_dated_today_in_the_tax_timezone_is_said(owner):  # noqa: F811
    """"Highest cost first" is offered only on a transaction dated today in
    the tax timezone (Q3), never one already in the past."""
    when = now_utc().isoformat().replace("+00:00", "Z")
    r = owner.post(URL, json=spend(when, "0.1", "10000"))
    assert r.status_code == 200, r.text
    assert r.json()["dated_today"] is True
    yesterday = (now_utc() - timedelta(days=1)).isoformat().replace("+00:00", "Z")
    assert owner.post(URL, json=spend(yesterday, "0.1", "10000")).json()["dated_today"] is False


def test_today_is_the_tax_timezones(owner):  # noqa: F811
    """A moment that is today in UTC but not in Chicago, the tax timezone:
    00:01 UTC today while Chicago's date is UTC's (it's still yesterday
    there), else 00:01 tomorrow in Chicago (already today in UTC)."""
    assert owner.put("/api/settings/tax-timezone", json={"timezone": "America/Chicago", "chosen": True}) \
        .status_code == 200
    chicago = ZoneInfo("America/Chicago")
    now = now_utc()
    if now.astimezone(chicago).date() == now.date():
        moment = now.replace(hour=0, minute=1, second=0)
    else:
        tomorrow = now.astimezone(chicago).date() + timedelta(days=1)
        moment = datetime(tomorrow.year, tomorrow.month, tomorrow.day, 0, 1, tzinfo=chicago).astimezone(timezone.utc)
    assert moment.date() == now.date() and moment.astimezone(chicago).date() != now.astimezone(chicago).date()
    r = owner.post(URL, json=spend(moment.isoformat().replace("+00:00", "Z"), "0.1", "10000"))
    assert r.status_code == 200, r.text
    assert r.json()["dated_today"] is False


def test_a_dollar_withdrawal_or_a_buy_lists_no_coins(owner):  # noqa: F811
    for body in ({"type": "Withdrawal", "timestamp": LEAVES, "from_account_id": 1, "to_account_id": 99,
                  "amount": "100", "fee_amount": "0"},
                 {"type": "Buy", "timestamp": LEAVES, "from_account_id": 1, "to_account_id": EXCHANGE_BTC,
                  "amount": "0.1", "fee_amount": "0", "fee_currency": "USD"}):
        r = owner.post(URL, json=body)
        assert r.status_code == 422, r.text
        assert r.json()["detail"] == NOT_LISTED


def test_a_withdrawal_from_an_exchange_lists_no_coins(owner):  # noqa: F811
    buy(owner, "2025-02-01T12:00:00Z", "1", "100000")
    r = owner.post(URL, json=spend(LEAVES, "0.1", "10000", frm=EXCHANGE_BTC))
    assert r.status_code == 422, r.text
    assert r.json()["detail"] == NOT_LISTED


# The past-year question (6.2)


def test_a_choice_added_in_an_earlier_year_brings_its_line(owner, tax_year):  # noqa: F811
    ids = owner.ids
    s = saved(owner.post("/api/transactions", json=spend(LEAVES, "0.1", "10000", "0.0001")))
    tax_year(2026)
    asked = owner.put(f"/api/transactions/{s}", json=spend(LEAVES, "0.1", "10000", "0.0001",
                                                           coins((ids["A2"], "0.1001"))))
    assert asked.status_code == 409, asked.text
    assert asked.json()["coins_chosen"] == CHOICE_LINE
    added = owner.post("/api/transactions", json=spend("2025-07-01T12:00:00Z", "0.01", "1000",
                                                       chosen=coins((ids["A2"], "0.01"))))
    assert added.status_code == 409, added.text
    assert added.json()["coins_chosen"] == CHOICE_LINE


def test_an_earlier_years_write_that_leaves_a_choice_as_it_is_brings_no_line(chose_a2, tax_year):  # noqa: F811
    ids = chose_a2.ids
    tax_year(2026)
    for body in ({"proceeds_usd": "12000"},
                 spend(LEAVES, "0.1", "12000", "0.0001", coins((ids["A2"], "0.10010000")))):  # sent back unchanged
        asked = chose_a2.put(f"/api/transactions/{ids['S']}", json=body)
        assert asked.status_code == 409, asked.text
        assert asked.json().get("coins_chosen") is None
    asked = chose_a2.delete(f"/api/transactions/{ids['S']}")
    assert asked.status_code == 409, asked.text
    assert asked.json().get("coins_chosen") is None


def test_setting_a_choice_back_to_oldest_first_brings_no_line(chose_a2, tax_year):  # noqa: F811
    """Oldest first is the IRS's default: it needs no record of a choice."""
    tax_year(2026)
    asked = chose_a2.put(f"/api/transactions/{chose_a2.ids['S']}", json={"chosen_coins": None})
    assert asked.status_code == 409, asked.text
    assert asked.json().get("coins_chosen") is None


def test_oldest_first_follows_the_save_where_two_purchases_share_a_date(owner):  # noqa: F811
    """X and Y, both originally acquired 2016-05-05: X reaches Wallet in two
    transfers, one before Y's deposit and one after, so Wallet's lots in the
    save's order (date acquired, then the first made) are X 0.1, Y 0.05,
    X 0.1. Spending 0.15 oldest first takes X's first 0.1 and Y's 0.05,
    never X's second lot: what the picker fills is what the save takes (the
    review's)."""
    x = deposit(owner, "2024-01-10T12:00:00Z", "0.2", "200", acquired="2016-05-05", to=EXCHANGE_BTC)
    saved(owner.post("/api/transactions", json=transfer("2024-02-01T12:00:00Z", "0.1", frm=EXCHANGE_BTC, to=WALLET)))
    y = deposit(owner, "2024-03-01T12:00:00Z", "0.05", "2500", acquired="2016-05-05")
    saved(owner.post("/api/transactions", json=transfer("2024-04-01T12:00:00Z", "0.1", frm=EXCHANGE_BTC, to=WALLET)))
    r = owner.post(URL, json=spend(LEAVES, "0.15", "15000"))
    assert r.status_code == 200, r.text
    first = {line["acquired_txn_id"]: line["oldest_first"] for line in r.json()["held"]}
    assert (first[x], first[y]) == ("0.10000000", "0.05000000")
    assert sorted((c["acquired_txn_id"], c["btc"]) for c in r.json()["coins"]) == \
        sorted([(x, "0.10000000"), (y, "0.05000000")])


def test_a_move_within_one_wallet_holds_nothing_to_choose_from(owner):  # noqa: F811
    """A consolidation records only its fee, oldest first: no picker."""
    r = owner.post(URL, json=transfer(LEAVES, "0.4", "0.0001", to=WALLET))
    assert r.status_code == 200, r.text
    assert r.json()["held"] is None
