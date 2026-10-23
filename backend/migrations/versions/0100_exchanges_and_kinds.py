"""2.0's first migration: exchanges, and each account's kind (2.0 spec 5.2, 5.3).

A new table, exchanges (id, name unique ignoring ASCII case, sends_1099da),
and three new columns in accounts: kind ("bank", "wallet", "exchange" or
"fee"), exchange_id (an exchange's two accounts only) and hidden; name
becomes COLLATE NOCASE.

- Exchange 1, "Exchange", is written only when accounts 3 or 4 exist: a
  restore copies a backup's rows into a database its migrations made, where
  a row of the migration's own would clash (seed_defaults makes it on a
  fresh install).
- The kinds: 1 bank, 2 wallet, 3 and 4 exchange 1's, 5 and 6 fee. Any other
  row (made through 1.x's account API) is a wallet if its currency is BTC,
  else a bank, never an exchange, which is a pair; but a row with
  External's id (99), or a second "BTC Fees" or "USD Fees" (#289), is an
  internal fee account.
- The names of rows beyond 1-6 (1.x took any text): trimmed, NFC, a control
  or format character a space (but the zero-width joiners), every run of
  spaces one, at most 40 characters, "account N" when nothing is left; one
  that is a reserved name or alike another (normalised and casefolded, the
  lower id keeping it) gets " (account N)", or " (account N, 2)" and on.
  Ids 1-6 keep theirs: seed_defaults then gives 5 and 6 their names back,
  which a second "BTC Fees" no longer stops.

accounts is rebuilt under its own name (the old table moved aside first,
with the other tables' references left naming accounts), so its stored
definition is what a fresh install's is. No transaction, ledger line, lot or
disposal is touched, and nothing is recalculated: no figure moves.

The way back to 0012 drops the new table and columns; names it changed stay
changed.

Revision ID: 0100
Revises: 0012
Create Date: 2026-10-23
"""

import re
import unicodedata

from alembic import op
import sqlalchemy as sa

revision = "0100"
down_revision = "0012"
branch_labels = None
depends_on = None

# 2.0's first migration: backend/migrate.py walks down to it, so every
# revision below it is 1.x's, whose databases get the pre-2.0 copy
STARTS_2_0 = True

# (kind, exchange) of the fixed accounts (database.FIXED_ACCOUNTS)
FIXED_KINDS = {1: ("bank", None), 2: ("wallet", None), 3: ("exchange", 1), 4: ("exchange", 1),
               5: ("fee", None), 6: ("fee", None)}
EXTERNAL = 99
RESERVED_NAMES = ("Bank", "Wallet", "Exchange USD", "Exchange BTC", "BTC Fees", "USD Fees", "External")
FEE_NAMES = ("BTC Fees", "USD Fees")
LONGEST_NAME = 40
# Some scripts and emoji need them: the one format characters a name keeps
JOINERS = ("‌", "‍")


def upgrade() -> None:
    op.create_table(
        "exchanges",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(collation="NOCASE"), nullable=False),
        sa.Column("sends_1099da", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_exchanges_id", "exchanges", ["id"])
    op.execute("INSERT INTO exchanges (id, name, sends_1099da) "
               "SELECT 1, 'Exchange', 1 WHERE EXISTS (SELECT 1 FROM accounts WHERE id IN (3, 4))")
    rows = op.get_bind().execute(sa.text("SELECT id, user_id, name, currency FROM accounts ORDER BY id")).all()
    names = free_names([(row.id, row.name) for row in rows])
    _rebuild_accounts(_columns_2_0(), [
        {"id": row.id, "user_id": row.user_id, "name": names[row.id], "currency": row.currency,
         **_kind(row.id, row.name, row.currency), "hidden": False}
        for row in rows])


def downgrade() -> None:
    rows = op.get_bind().execute(sa.text("SELECT id, user_id, name, currency FROM accounts ORDER BY id")).all()
    _rebuild_accounts(_columns_1x(), [dict(row._mapping) for row in rows])
    op.drop_index("ix_exchanges_id", table_name="exchanges")
    op.drop_table("exchanges")


def _kind(account_id: int, name: str, currency: str) -> dict:
    if account_id in FIXED_KINDS:
        kind, exchange = FIXED_KINDS[account_id]
        return {"kind": kind, "exchange_id": exchange}
    if account_id == EXTERNAL or _key(_clean(name)) in {_key(fee) for fee in FEE_NAMES}:
        return {"kind": "fee", "exchange_id": None}
    return {"kind": "wallet" if currency == "BTC" else "bank", "exchange_id": None}


def free_names(rows: list[tuple[int, str]]) -> dict[int, str]:
    """Each account's name by id: 1-6 as they are, every other cleaned and
    made free of the reserved names and of each other, lowest id first."""
    names = {account_id: name for account_id, name in rows if account_id in FIXED_KINDS}
    taken = {_key(name) for name in (*RESERVED_NAMES, *names.values())}
    for account_id, name in sorted((i, n) for i, n in rows if i not in FIXED_KINDS):
        clean = _clean(name) or f"account {account_id}"
        free, tries = clean[:LONGEST_NAME], 1
        while _key(free) in taken:
            suffix = f" (account {account_id})" if tries == 1 else f" (account {account_id}, {tries})"
            free = clean[:LONGEST_NAME - len(suffix)].rstrip() + suffix
            tries += 1
        taken.add(_key(free))
        names[account_id] = free
    return names


def _clean(name: str | None) -> str:
    """One line of plain text: NFC, a control or format character a space
    (but the joiners), every run of spaces one, trimmed."""
    text = "".join(" " if _not_text(c) or unicodedata.category(c) == "Zs" else c
                   for c in unicodedata.normalize("NFC", name or ""))
    return re.sub(" +", " ", text).strip()


def _not_text(c: str) -> bool:
    category = unicodedata.category(c)
    return category in ("Cc", "Zl", "Zp") or (category == "Cf" and c not in JOINERS)


def _key(name: str) -> str:
    """Two names are alike when this is the same (2.0 spec 5.1)."""
    return unicodedata.normalize("NFC", unicodedata.normalize("NFC", name).casefold())


def _columns_2_0() -> tuple:
    return (
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(collation="NOCASE"), nullable=False),
        sa.Column("currency", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("exchange_id", sa.Integer(), nullable=True),
        sa.Column("hidden", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.UniqueConstraint("name"),
        sa.ForeignKeyConstraint(["exchange_id"], ["exchanges.id"]),  # where a fresh install's table has it
    )


def _columns_1x() -> tuple:
    """As the baseline (0001) made accounts."""
    return (
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("currency", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.UniqueConstraint("name"),
    )


def _rebuild_accounts(columns: tuple, rows: list[dict]) -> None:
    """accounts made again under its own name, with `rows`, in one copy. The
    old table is moved aside with SQLite's legacy rename, which leaves the
    other tables' references naming accounts (a rename would otherwise point
    them at the old table, then gone); SQLite's foreign keys are off, as
    always in BitcoinTX, so nothing checks them meanwhile."""
    op.execute("PRAGMA legacy_alter_table = ON")
    op.drop_index("ix_accounts_id", table_name="accounts")
    op.rename_table("accounts", "_accounts_old")
    table = op.create_table("accounts", *columns)
    if rows:
        op.bulk_insert(table, rows)
    op.drop_table("_accounts_old")
    op.create_index("ix_accounts_id", "accounts", ["id"])
    op.execute("PRAGMA legacy_alter_table = OFF")
