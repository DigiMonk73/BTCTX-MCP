"""
The reference ledger's 2.0 rows (2.0 spec 5.15; card B7a #354): its
`accounts` list adds two of each kind (wallets Coldcard and Jade, exchanges
Kraken and Overseas, banks Credit union and Savings) and a fourth wallet,
the Sparrow, which scripts/seed_ledger.py makes through the account API
before the rows, and its "since": "2.0" rows use only those (B7a's in 2026;
#702's from 2022 to 2026, each for the year it fills; #730's, which choose
coins, in 2025 and 2026), but one: the split of a pooled wallet, a Transfer
from Wallet to the Coldcard with no fee, after every row that takes coins
from either.

- Every old row keeps its figures with the new rows beside it
  (test_old_rows_keep_their_figures): 1.x's beside every 2.0 row
  (equivalence_check's ledgers leave those out, B1, so this is their
  proof); 1.x's and B7a's beside #702's and #730's (each "added"), which go
  into the same 2.0 accounts only after each one's last earlier disposal
  (Kraken's and Overseas' bitcoin emptied by the end of 2025); and 1.x's,
  B7a's and #702's beside #730's, the Sparrow's, which send chosen coins
  to the Jade and Kraken only after each one's last earlier row.
- The split row moves only Wallet's and the Coldcard's year-end lots and
  balances.
- The seed makes the accounts with the ids the ledger lists, uses again
  those a Delete All left, stops when an id comes out otherwise, and seeds
  given rows (a 1.x release's, make_reference_1x_db.py) without the account
  API, which a 1.x release lacks.
"""

import importlib.util
import json
import re
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.models.exchange import Exchange
from backend.models.transaction import BitcoinLot, LotDisposal, Transaction
from backend.services import first_run, outbound
from backend.services.account import account_book
from backend.services.reports.form_8949 import disposal_box
from backend.services.tax_time import get_tax_timezone, local_date

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
WALLET, COLDCARD, EXTERNAL = 2, 100, 99
NEW_ACCOUNTS = set(range(100, 109))
USER, PASSWORD = "seed-user", "seed-password-123"


def _script(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


seed_ledger = _script("seed_ledger")
reference_figures = _script("reference_figures")


def raw_rows() -> list[dict]:
    """The ledger's rows as written, with their notes."""
    return json.loads(seed_ledger.LEDGER.read_text())["transactions"]


def split_row() -> dict:
    [split] = [r for r in raw_rows() if "since" in r and r["from_account_id"] == WALLET]
    return split


@pytest.fixture
def owner(fresh_app, monkeypatch):
    """A fresh install claimed by the seed's login, price source Off; yields (client, Session)."""
    async def find_prices(day, full):
        raise AssertionError(f"a price was asked for: {day}")

    monkeypatch.setattr("backend.services.price_history.find_prices", find_prices)
    monkeypatch.setattr(outbound, "_current", outbound.NetworkSettings(price_source="off"))
    c = TestClient(app)
    seed_ledger.log_in(c, USER, PASSWORD, first_run.ensure_code())
    return c, fresh_app


def delete_all(c: TestClient) -> None:
    assert c.delete("/api/transactions/delete_all?confirm=DELETE").status_code == 204


def seed_without(c: TestClient, leave_out) -> list[dict]:
    """The ledger's rows (notes and all) but those `leave_out` picks, seeded
    after its accounts; returns the rows sent, in order."""
    kept = [(raw, sent) for raw, sent in zip(raw_rows(), seed_ledger.ledger_rows()) if not leave_out(raw)]
    seed_ledger.seed(c, [sent for _, sent in kept], seed_ledger.ledger_accounts())
    return [raw for raw, _ in kept]


def old_rows_figures(Session, sent: list[dict], newer=lambda raw: "since" in raw) -> list[dict]:
    """Each row's figures but those `newer` picks (1.x's by default), in the
    ledger's order: its own stored ones (a deposit's value at receipt is
    its income), every disposal it made (BTC, proceeds, basis, gain, term,
    box, and its lot's date acquired: Form 8949's column (b)) and every lot
    it made (BTC, date, cost; not what's left of it, which the split row,
    and later rows taking from it, change)."""
    with Session() as db:
        book, tz = account_book(db), get_tax_timezone(db)
        txs = db.query(Transaction).order_by(Transaction.id).all()
        assert len(txs) == len(sent)
        figures = []
        for tx, raw in zip(txs, sent):
            if newer(raw):
                continue
            year = local_date(tx.timestamp, tz).year
            disposals = db.query(LotDisposal).filter(LotDisposal.transaction_id == tx.id)
            lots = db.query(BitcoinLot).filter(BitcoinLot.created_txn_id == tx.id)
            figures.append({
                "row": (tx.type, tx.timestamp, tx.from_account_id, tx.to_account_id, str(tx.amount)),
                "stored": [str(getattr(tx, f)) for f in ("cost_basis_usd", "proceeds_usd", "gross_proceeds_usd",
                                                         "realized_gain_usd", "holding_period", "fee_usd", "fmv_usd")],
                "disposals": sorted((str(d.disposed_btc), str(d.proceeds_usd_for_that_portion),
                                     str(d.disposal_basis_usd), str(d.realized_gain_usd), d.holding_period,
                                     bool(d.is_fee), disposal_box(d, year, tz, book), d.lot.acquired_date.isoformat())
                                    for d in disposals),
                "lots": sorted((str(lot.total_btc), lot.acquired_date.isoformat(), str(lot.cost_basis_usd))
                               for lot in lots),
            })
        return figures


@pytest.mark.parametrize("newer", [lambda raw: "since" in raw, lambda raw: "added" in raw,
                                   lambda raw: raw.get("added") == "#730"], ids=["2.0", "#702 on", "#730"])
def test_old_rows_keep_their_figures(owner, newer):
    c, Session = owner
    with_new = old_rows_figures(Session, seed_without(c, lambda raw: False), newer)
    delete_all(c)
    alone = old_rows_figures(Session, seed_without(c, newer), newer)
    assert len(alone) == len([r for r in raw_rows() if not newer(r)])
    assert with_new == alone


def test_the_new_rows_use_only_new_accounts_but_the_split():
    """2.0 spec 5.15: deposits from External fund them; the one exception
    is the split, from Wallet (and its date is checked, not trusted). A new
    row moves its year's totals and the holdings after it, never an older
    row's figures (test_old_rows_keep_their_figures)."""
    new = [r for r in raw_rows() if "since" in r]
    assert {r["since"] for r in new} == {"2.0"}
    assert all("since" in r for r in raw_rows() if "added" in r)  # so a 1.x release never gets one
    assert all({r["from_account_id"], r["to_account_id"]} <= NEW_ACCOUNTS | {EXTERNAL} for r in new if r != split_row())
    assert (split_row()["to_account_id"], split_row()["fee_amount"]) == (COLDCARD, "0")


def test_the_split_is_the_last_row_wallet_or_the_coldcard_names():
    """After every row that takes coins from either (or puts any in), so it
    moves only what each holds at the end."""
    split = split_row()
    naming = [r for r in raw_rows() if {WALLET, COLDCARD} & {r["from_account_id"], r["to_account_id"]}]
    assert max(r["timestamp"] for r in naming if r != split) < split["timestamp"]


def _without_holdings(year: dict) -> dict:
    return {**year, "report": {k: v for k, v in year["report"].items() if k != "end_of_year_balances"}}


def _holdings(year: dict, accounts: set[str], inside: bool) -> list[dict]:
    return [lot for lot in year["report"]["end_of_year_balances"] if (lot.get("account") in accounts) == inside]


def test_the_split_row_moves_only_wallets_and_the_coldcards_lots_and_balances(owner):
    c, Session = owner
    seed_without(c, lambda raw: False)
    with Session() as db:
        split = reference_figures.figures(db)
    delete_all(c)
    seed_without(c, lambda raw: raw == split_row())
    with Session() as db:
        unsplit = reference_figures.figures(db)

    for year in ("2023", "2024", "2025"):
        assert split["years"][year] == unsplit["years"][year], year
    after, before = split["years"]["2026"], unsplit["years"]["2026"]
    assert _without_holdings(after) == _without_holdings(before)  # every Form 8949 row, gain and income
    both = {"Wallet", "Coldcard"}
    assert _holdings(after, both, inside=False) == _holdings(before, both, inside=False)
    for column in ("quantity", "cost"):  # the same coins, only where they are differs
        assert sum(Decimal(str(lot[column])) for lot in _holdings(after, both, inside=True)) == \
            sum(Decimal(str(lot[column])) for lot in _holdings(before, both, inside=True)), column

    balances = {b["account_id"]: Decimal(b["balance"]) for b in split["dashboard"]["balances"]}
    unsplit_balances = {b["account_id"]: Decimal(b["balance"]) for b in unsplit["dashboard"]["balances"]}
    moved = Decimal(split_row()["amount"])
    assert (balances.pop(WALLET), balances.pop(COLDCARD)) == (unsplit_balances.pop(WALLET) - moved,
                                                              unsplit_balances.pop(COLDCARD) + moved)
    assert balances == unsplit_balances
    assert {k: v for k, v in split["dashboard"].items() if k != "balances"} == \
        {k: v for k, v in unsplit["dashboard"].items() if k != "balances"}


# The seed and the account API
def test_the_ledgers_accounts_are_made_with_their_ids(owner):
    c, Session = owner
    assert seed_ledger.seed(c) == len(raw_rows())
    listed = json.loads(seed_ledger.LEDGER.read_text())["accounts"]
    made = {a["id"]: (a["name"], a["kind"], a["currency"]) for a in c.get("/api/accounts/").json()}
    assert {a["id"]: (a["name"], a["kind"], a["currency"]) for a in listed}.items() <= made.items()
    with Session() as db:
        assert dict(db.query(Exchange.name, Exchange.sends_1099da)) == {
            "Exchange": True, "Kraken": True, "Overseas": False}


def test_seeding_again_after_delete_all_uses_the_accounts_left(owner):
    c, _ = owner
    seed_ledger.seed(c)
    before = c.get("/api/accounts/").json()
    delete_all(c)
    assert seed_ledger.seed(c) == len(raw_rows())
    assert [(a["id"], a["name"]) for a in c.get("/api/accounts/").json()] == [(a["id"], a["name"]) for a in before]


def test_seeding_again_puts_a_switch_changed_by_hand_back(owner):
    """Kraken's and 1.x's own exchange's: both on in the ledger."""
    c, Session = owner
    seed_ledger.seed(c)
    for account in (103, 4):  # Kraken BTC, Exchange BTC
        assert c.put(f"/api/accounts/{account}", json={"sends_1099da": False}).status_code == 200
    delete_all(c)
    seed_ledger.seed(c)
    with Session() as db:
        assert dict(db.query(Exchange.name, Exchange.sends_1099da)) == {
            "Exchange": True, "Kraken": True, "Overseas": False}


def test_an_account_is_made_under_its_old_name_and_renamed_after_the_rows(owner):
    """#702: Overseas is made as "Offshore" and renamed once its rows are in
    (the exchange and both its accounts), and the Jade is hidden then,
    still holding coins: as an owner renames or hides an account in use."""
    c, Session = owner
    sent = c.request
    writes = []

    def noted(method, url, **kwargs):
        if method in ("POST", "PUT"):
            writes.append((method, str(url).split("?")[0], kwargs.get("json")))
        return sent(method, url, **kwargs)

    c.request = noted
    seed_ledger.seed(c)
    made = [body["name"] for method, url, body in writes if (method, url) == ("POST", "/api/accounts/")]
    assert "Offshore" in made and "Overseas" not in made
    renamed = [i for i, (method, _, body) in enumerate(writes) if method == "PUT" and body.get("name") == "Overseas"]
    last_row = max(i for i, (method, url, _) in enumerate(writes) if (method, url) == ("POST", "/api/transactions"))
    assert len(renamed) == 1 and renamed[0] > last_row
    assert writes[renamed[0]][1:] == ("/api/accounts/104", {"name": "Overseas", "hidden": False})
    with Session() as db:
        assert dict(db.query(Exchange.id, Exchange.name)) == {1: "Exchange", 2: "Kraken", 3: "Overseas"}
    accounts = {a["id"]: a for a in c.get("/api/accounts/").json()}
    assert (accounts[104]["name"], accounts[105]["name"]) == ("Overseas USD", "Overseas BTC")
    assert [i for i, a in accounts.items() if a["hidden"]] == [101]
    assert c.get("/api/calculations/account/101/balance").json()["balance"] > 0


def test_seeding_again_puts_back_an_account_hidden_or_shown_by_hand(owner):
    c, _ = owner
    seed_ledger.seed(c)
    for account, hidden in ((101, False), (107, True)):  # the Jade shown, Savings hidden
        assert c.put(f"/api/accounts/{account}", json={"hidden": hidden}).status_code == 200
    delete_all(c)
    seed_ledger.seed(c)
    assert [a["id"] for a in c.get("/api/accounts/").json() if a["hidden"]] == [101]


def test_accounts_given_with_the_ledgers_rows_are_the_ones_made(owner):
    """None given: none made, so the first row into a new account is refused."""
    c, _ = owner
    with pytest.raises(seed_ledger.SeedError, match="Unknown account id 103"):  # 2022's deposit into Kraken
        seed_ledger.seed(c, accounts=[])


def test_an_account_that_would_get_another_id_stops_the_seed(owner):
    c, Session = owner
    assert c.post("/api/accounts/", json={"kind": "wallet", "name": "Spare"}).status_code == 201  # takes 100
    with pytest.raises(seed_ledger.SeedError, match="Coldcard is account 101 here"):
        seed_ledger.seed(c)
    with Session() as db:
        assert db.query(Transaction).count() == 0


def test_given_rows_alone_never_call_the_account_api(owner):
    """make_reference_1x_db.py seeds a 1.x release's app, which has no 2.0
    account API, with the ledger's 1.x rows."""
    c, _ = owner
    paths = []
    sent = c.request

    def noted(method, url, **kwargs):
        paths.append(str(url))
        return sent(method, url, **kwargs)

    c.request = noted
    rows = [sent_row for raw, sent_row in zip(raw_rows(), seed_ledger.ledger_rows()) if "since" not in raw]
    assert seed_ledger.seed(c, rows) == len(rows)
    assert paths and not [p for p in paths if "/api/accounts" in p]


def test_an_exchange_whose_accounts_disagree_on_its_switch_stops_the_seed(tmp_path, monkeypatch):
    ledger = tmp_path / "ledger.json"
    ledger.write_text(json.dumps({"accounts": [
        {"id": 102, "name": "Kraken USD", "kind": "exchange", "currency": "USD", "exchange_id": 2, "sends_1099da": True},
        {"id": 103, "name": "Kraken BTC", "kind": "exchange", "currency": "BTC", "exchange_id": 2,
         "sends_1099da": False}], "transactions": []}))
    monkeypatch.setattr(seed_ledger, "LEDGER", ledger)
    with pytest.raises(seed_ledger.SeedError, match="disagree on its 1099-DA switch"):
        seed_ledger.ledger_accounts()


@pytest.mark.parametrize("note, usd, btc, said", [
    ("hidden", True, False, "disagree on whether it's hidden"),
    ("renamed_from", "Old USD", "Older BTC", "disagree on the name it had"),
])
def test_an_exchange_whose_accounts_disagree_on_a_note_stops_the_seed(tmp_path, monkeypatch, note, usd, btc, said):
    ledger = tmp_path / "ledger.json"
    ledger.write_text(json.dumps({"accounts": [
        {"id": 102, "name": "Kraken USD", "kind": "exchange", "currency": "USD", "exchange_id": 2, note: usd},
        {"id": 103, "name": "Kraken BTC", "kind": "exchange", "currency": "BTC", "exchange_id": 2, note: btc}],
        "transactions": []}))
    monkeypatch.setattr(seed_ledger, "LEDGER", ledger)
    with pytest.raises(seed_ledger.SeedError, match=said):
        seed_ledger.ledger_accounts()


# A choice's keys (#711, docs/temp/2.0-coin-choice.md 8.3): a row names the
# coins it acquired, and a later row chooses them by that name
OLDER = {"type": "Deposit", "timestamp": "2025-01-09T12:00:00Z", "from_account_id": EXTERNAL,
         "to_account_id": WALLET, "amount": "0.01", "fee_amount": "0", "fee_currency": "BTC", "source": "MyBTC",
         "cost_basis_usd": "400.00", "acquired_at": "2023-01-09"}
NEWER = {**OLDER, "timestamp": "2025-01-10T12:00:00Z", "cost_basis_usd": "900.00", "acquired_at": "2025-01-10"}


def _spend(chosen: list[dict]) -> dict:
    return {"type": "Withdrawal", "timestamp": "2025-03-10T12:00:00Z", "from_account_id": WALLET,
            "to_account_id": EXTERNAL, "amount": "0.004", "fee_amount": "0", "fee_currency": "BTC",
            "purpose": "Spent", "gross_proceeds_usd": "400.00", "chosen_coins": chosen}


def test_a_choice_names_its_coins_by_the_id_their_row_got(owner):
    """The key is never sent: the server is told the id it gave the key's
    row, in a Delete All's ledger again too."""
    c, Session = owner
    sent = c.request
    posted = []

    def noted(method, url, **kwargs):
        if (method, str(url).split("?")[0]) == ("POST", "/api/transactions"):
            posted.append(kwargs.get("json"))
        return sent(method, url, **kwargs)

    c.request = noted
    rows = [OLDER, {**NEWER, "key": "newer"}, _spend([{"key": "newer", "btc": "0.004"}])]
    for _ in range(2):
        assert seed_ledger.seed(c, rows) == 3
        with Session() as db:
            _, newer = db.query(Transaction).filter(Transaction.type == "Deposit").order_by(Transaction.timestamp)
            spend = db.query(Transaction).filter(Transaction.type == "Withdrawal").one()
            assert [(coin.acquired_txn_id, str(coin.btc)) for coin in spend.chosen_coins] == [(newer.id, "0.00400000")]
            # the newer coins' cost, $900 x 0.4, not the older ones' $160
            assert [str(d.disposal_basis_usd) for d in spend.lot_disposals] == ["360.00"]
        delete_all(c)
    assert not [body for body in posted if "key" in body]
    assert [line for body in posted for line in body.get("chosen_coins") or []] == [
        {"acquired_txn_id": line_id, "btc": "0.004"} for line_id in (2, 2)]


def test_a_choice_is_sent_with_the_id_the_server_gave_never_the_rows_place():
    """On a fresh install the two are the same number, so a create that
    answers other ids tells them apart."""
    created = []

    def create(n: int, row: dict) -> int:
        created.append(row)
        return n + 100

    seed_ledger.create_rows([OLDER, {**NEWER, "key": "newer"}, _spend([{"key": "newer", "btc": "0.004"}])], create)
    assert created == [OLDER, NEWER, _spend([{"acquired_txn_id": 102, "btc": "0.004"}])]


@pytest.mark.parametrize("rows, said", [
    ([{**OLDER, "key": "k"}, {**NEWER, "key": "k"}], "row 2's key 'k' is row 1's too: a key names one Buy or Deposit"),
    ([_spend([{"key": "k", "btc": "0.004"}]), {**NEWER, "key": "k"}],
     "row 1 chooses coins by the key 'k', which no row before it has"),
    ([NEWER, _spend([{"key": "z", "btc": "0.004"}])], "row 2 chooses coins by the key 'z', which no row before it has"),
    ([NEWER, _spend([{"acquired_txn_id": 1, "btc": "0.004"}])], "row 2 chooses coins without a key"),
    ([NEWER, {**_spend([]), "key": "s"}], "row 2 is a Withdrawal with a key: only a Buy or a Deposit acquires coins"),
], ids=["a key twice", "a choice before its key", "a key no row has", "a line without a key", "a key on a spend"])
def test_a_key_the_seed_cant_follow_stops_it_before_anything_is_sent(owner, rows, said):
    c, Session = owner
    sent = c.request
    writes = []

    def noted(method, url, **kwargs):
        if method != "GET":
            writes.append((method, str(url)))
        return sent(method, url, **kwargs)

    c.request = noted
    with pytest.raises(seed_ledger.SeedError, match=re.escape(said)):
        seed_ledger.seed(c, rows, seed_ledger.ledger_accounts())
    assert writes == []  # neither an account nor a row
    with Session() as db:
        assert db.query(Transaction).count() == 0


def test_a_ledger_without_an_accounts_list_adds_none(tmp_path, monkeypatch):
    ledger = tmp_path / "ledger.json"
    ledger.write_text(json.dumps({"transactions": []}))
    monkeypatch.setattr(seed_ledger, "LEDGER", ledger)
    assert seed_ledger.ledger_accounts() == []
