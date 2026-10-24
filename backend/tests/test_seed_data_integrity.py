import pytest
from decimal import Decimal
from collections import defaultdict
from datetime import datetime, timezone

from backend.models.transaction import Transaction, LedgerEntry, BitcoinLot, LotDisposal
from backend.models.account import Account


def _ts(year, month, day):
    return datetime(year, month, day, 12, 0, 0, tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# This module's own ledger: every main account gets a balance, a BTC fee a
# disposal, a sale a disposal
SEED = [
    # 1. Deposit USD to Bank
    {"type": "Deposit", "timestamp": _ts(2024, 1, 1), "from_account_id": 99, "to_account_id": 1,
     "amount": "100000", "is_income": False},
    # 2. Transfer USD from Bank to Exchange USD
    {"type": "Transfer", "timestamp": _ts(2024, 1, 5), "from_account_id": 1, "to_account_id": 3,
     "amount": "50000"},
    # 3. Buy BTC
    {"type": "Buy", "timestamp": _ts(2024, 2, 1), "from_account_id": 3, "to_account_id": 4,
     "amount": "1.0", "cost_basis_usd": "40000"},
    # 4. Transfer BTC with a fee to Wallet (the fee is a disposal)
    {"type": "Transfer", "timestamp": _ts(2024, 3, 1), "from_account_id": 4, "to_account_id": 2,
     "amount": "0.5", "fee_amount": "0.0001", "fee_currency": "BTC"},
    # 5. Sell BTC (a disposal)
    {"type": "Sell", "timestamp": _ts(2024, 4, 1), "from_account_id": 4, "to_account_id": 3,
     "amount": "0.25", "proceeds_usd": "15000"},
]


def _wipe(client):
    r = client.delete("/api/transactions/delete_all?confirm=DELETE")
    assert r.status_code == 204, r.text


def _seed_own_ledger(client, db):
    """
    Give this module the ledger it checks, whatever the shared session
    database holds. Run in parallel (pytest -n auto), a worker can reach this
    module with another module's transactions in it, whose balances these
    checks don't describe; seeding only an empty database then checked those
    (#598). So it empties the database first, and every row must save.
    """
    _wipe(client)
    for row in SEED:
        r = client.post("/api/transactions", json=row)
        assert r.status_code == 200, r.text
    # End the session's read transaction so it sees the API's writes
    # (expire_all alone keeps SQLite's pre-seed snapshot)
    db.rollback()


@pytest.fixture(scope="module")
def db_session(auth_client, test_engine):
    """
    Provide a FRESH database session with test data. The shared session-scoped
    test_db can hold stale identity-map rows from other modules (ledger IDs are
    reused after delete/re-lot), which made balances read as zero.
    """
    from sqlalchemy.orm import sessionmaker
    db = sessionmaker(bind=test_engine)()
    try:
        _seed_own_ledger(auth_client, db)
        yield db
    finally:
        db.close()
        _wipe(auth_client)


def _balances(db):
    balances = defaultdict(float)
    for entry in db.query(LedgerEntry).all():
        balances[entry.account_id] += float(entry.amount)
    return balances


def test_its_own_ledger_whatever_another_module_left(auth_client, test_engine):
    """#598: another module's transactions in the shared database (a lone
    bitcoin deposit, no dollars) don't stand in for this module's ledger."""
    from sqlalchemy.orm import sessionmaker
    db = sessionmaker(bind=test_engine)()
    try:
        _wipe(auth_client)
        r = auth_client.post("/api/transactions", json={
            "type": "Deposit", "timestamp": _ts(2023, 6, 1), "from_account_id": 99, "to_account_id": 2,
            "amount": "0.1", "source": "MyBTC", "cost_basis_usd": "3000",
        })
        assert r.status_code == 200, r.text
        _seed_own_ledger(auth_client, db)
        assert db.query(Transaction).count() == len(SEED)
        balances = _balances(db)
        assert balances[1] and balances[3], "Bank and Exchange USD hold this module's dollars"
    finally:
        db.close()
        _wipe(auth_client)


# ----------------------------
# Test 1: Core Account IDs
# ----------------------------
def test_accounts_exist(db_session):
    ids = [acct.id for acct in db_session.query(Account).all()]
    for expected_id in [1, 2, 3, 4, 5, 6]:
        assert expected_id in ids, f"Missing Account ID={expected_id}"

# ----------------------------
# Test 2: Transaction Count
# ----------------------------
def test_transaction_count(db_session):
    txs = db_session.query(Transaction).all()
    assert len(txs) == len(SEED), f"Expected this module's {len(SEED)} transactions, found {len(txs)}"

# ----------------------------
# Test 3: BitcoinLots for BTC-acquiring Deposits/Buys
# ----------------------------
def test_bitcoin_lots_created(db_session):
    txs = db_session.query(Transaction).all()
    btc_deposits_or_buys = []
    for tx in txs:
        if tx.type in ("Deposit", "Buy"):
            to_acct = db_session.get(Account, tx.to_account_id)
            if to_acct and to_acct.currency == "BTC":
                btc_deposits_or_buys.append(tx.id)

    lots = db_session.query(BitcoinLot).all()
    lot_tx_ids = [lot.created_txn_id for lot in lots]
    missing = [txid for txid in btc_deposits_or_buys if txid not in lot_tx_ids]
    assert not missing, f"Missing BitcoinLots for Deposit/Buy BTC transactions: {missing}"

# ----------------------------
# Test 4: FIFO Lots and Disposals Exist
# ----------------------------
def test_fifo_lot_tracking(db_session):
    lots = db_session.query(BitcoinLot).all()
    disposals = db_session.query(LotDisposal).all()
    assert lots, "Expected at least one BitcoinLot"
    assert disposals, "Expected at least one LotDisposal"

# ----------------------------
# Test 5: FMV Rules on Non-Sale Withdrawals
# ----------------------------
def test_fmv_logic_present_for_non_sale_withdrawals(db_session):
    withdrawals = db_session.query(Transaction).filter(Transaction.type == "Withdrawal").all()
    for tx in withdrawals:
        if tx.purpose in ("Gift", "Donation", "Lost"):
            # proceeds_usd should be None or 0 for non-sale withdrawals
            assert tx.proceeds_usd is None or tx.proceeds_usd == Decimal("0.00"), \
                f"Expected 0 or None proceeds on ID {tx.id}, got {tx.proceeds_usd}"
            # FMV should be set for these disposal types (if present)
            # Note: FMV may not always be populated depending on transaction creation
            if tx.fmv_usd is not None:
                assert tx.fmv_usd >= 0, f"Invalid FMV on {tx.purpose} withdrawal ID {tx.id}"

# ----------------------------
# Test 6: No Negative Lot Balances
# ----------------------------
def test_no_negative_lot_balances(db_session):
    broken = db_session.query(BitcoinLot).filter(BitcoinLot.remaining_btc < 0).all()
    assert not broken, "One or more lots have negative remaining_btc!"

# ----------------------------
# Test 7: Ledger Entry Count and Per-Tx Match
# ----------------------------
def test_ledger_entries_exist(db_session):
    txs = db_session.query(Transaction).all()
    total_ledger = db_session.query(LedgerEntry).count()

    def expected_entries(tx):
        fee = float(tx.fee_amount or 0)
        if tx.type in ("Buy", "Sell"):
            return 3 if fee > 0 else 2
        elif tx.type == "Transfer":
            return 3 if fee > 0 else 2
        elif tx.type in ("Deposit", "Withdrawal"):
            return 2 if fee > 0 else 1
        return 1

    expected_total = 0
    mismatches = []
    for tx in txs:
        exp = expected_entries(tx)
        actual = len(tx.ledger_entries)
        expected_total += exp
        if actual != exp:
            mismatches.append((tx.id, tx.type, exp, actual))

    assert not mismatches, f"LedgerEntry mismatches: {mismatches}"
    assert total_ledger == expected_total, f"Total LedgerEntry mismatch: expected {expected_total}, got {total_ledger}"

# ----------------------------
# Test 8: Account Ledger Balances
# ----------------------------
def test_account_balances_non_null(db_session):
    problems = _zero_balances(db_session)
    assert not problems, f"Zero balances detected: {problems}"


def test_an_unused_account_holds_nothing_rightly(db_session):
    """2.0: an account the owner added that no transaction names yet holds
    nothing, and that's no problem. Flushed, never committed: the shared
    session database keeps only 1.x's accounts."""
    owner = db_session.get(Account, 2).user_id
    db_session.add(Account(user_id=owner, name="Unused Wallet", currency="BTC", kind="wallet"))
    db_session.flush()
    try:
        assert not _zero_balances(db_session)
    finally:
        db_session.rollback()


def _zero_balances(db):
    """The accounts a transaction or a ledger line names that hold nothing,
    but the fee accounts. One that none names holds nothing rightly (2.0:
    an account added and not used yet)."""
    balances = _balances(db)
    named = set(balances)  # the accounts with a ledger line
    for tx in db.query(Transaction).all():
        named |= {tx.from_account_id, tx.to_account_id}

    problems = []
    for acct in db.query(Account).all():
        if acct.kind == "fee" or acct.id not in named:
            continue
        if abs(balances[acct.id]) == 0:
            problems.append((acct.id, acct.name, acct.currency))
    return problems

# ----------------------------
# Test 10: LotDisposal vs BTC Amount Consistency
# ----------------------------
def test_disposal_amount_matches_transaction(db_session):
    txs = db_session.query(Transaction).all()
    all_disposals = db_session.query(LotDisposal).all()
    tx_disposals = defaultdict(list)

    for disp in all_disposals:
        tx_disposals[disp.transaction_id].append(disp)

    problems = []

    for tx in txs:
        # Skip non-disposal transaction types
        if tx.type not in ("Sell", "Withdrawal", "Transfer"):
            continue

        # Check if this transaction involves BTC
        from_acct = db_session.get(Account, tx.from_account_id)
        fee_btc = float(tx.fee_amount or 0) if (tx.fee_currency or "").upper() == "BTC" else 0.0

        # Determine if this transaction should have disposals
        is_btc_sell_or_withdrawal = tx.type in ("Sell", "Withdrawal") and from_acct and from_acct.currency == "BTC"
        is_btc_fee_transfer = tx.type == "Transfer" and fee_btc > 0

        if not is_btc_sell_or_withdrawal and not is_btc_fee_transfer:
            # USD transfers or transfers with no BTC fee don't need disposals
            continue

        if tx.id not in tx_disposals:
            problems.append((tx.id, "Missing LotDisposals"))
            continue

        total_disposed = sum(float(d.disposed_btc) for d in tx_disposals[tx.id])

        # Compute expected disposal amount
        if tx.type in ("Sell", "Withdrawal"):
            expected_disposal = float(tx.amount or 0) + fee_btc
        elif tx.type == "Transfer":
            expected_disposal = fee_btc  # Transfer only disposes fee, not the transferred amount

        if round(total_disposed, 8) != round(expected_disposal, 8):
            problems.append((tx.id, f"Disposed {total_disposed}, expected {expected_disposal}"))

    assert not problems, f"LotDisposal mismatch: {problems}"
