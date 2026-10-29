"""
What the importer for any exchange says about rows it leaves out, and how
each ready-made mapping says to download its file, checked against each
exchange's export as public sources showed it on 2026-10-29 (#813): a
reason that's true of the row, so the owner knows whether to add it by hand.
"""

import io

import pytest

from backend.tests.conftest import stub_daily_prices

KRAKEN_HEADER = '"txid","refid","time","type","subtype","aclass","asset","wallet","amount","fee","balance"\n'
STRIKE_HEADER = ("Reference,Date & Time (UTC),Transaction Type,Amount USD,Fee USD,Amount BTC,Fee BTC,BTC Price,"
                 "Cost Basis (USD),Destination,Description,Transaction Hash,Note\n")


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    stub_daily_prices(monkeypatch, lambda day: 100000.0)


def preview(client, mapping_id: str, content: str) -> dict:
    r = client.post("/api/import/exchange/preview", data={"mapping_id": mapping_id},
                    files={"file": ("export.csv", io.BytesIO(content.encode()), "text/csv")})
    assert r.status_code == 200, r.text
    return r.json()


def warned(answer: dict) -> str:
    return "\n".join(w["message"] for w in answer["warnings"])


def test_a_kraken_transfer_with_no_subtype_is_never_called_a_move_within_kraken(auth_client):
    """A transfer with no subtype is an airdrop or a fork, a deal with
    Kraken's OTC desk, or a move to or from Kraken Futures (Kraken's ledger
    fields; BittyTax, rotki): it may move bitcoin in or out, so the owner is
    told to look."""
    content = KRAKEN_HEADER + (
        '"LD1","TD1","2025-07-01 00:00:00","transfer","","currency","BTC","spot / main",0.0100000000,0,0.01\n'
        '"LD2","TD2","2025-07-02 00:00:00","transfer","spottostaking","currency","BTC","spot / main",'
        '-0.0010000000,0,0.009\n'
        '"LD3","TD2","2025-07-02 00:00:00","transfer","stakingfromspot","currency","BTC.S","spot / main",'
        '0.0010000000,0,0.001\n')
    answer = preview(auth_client, "kraken", content)
    assert answer["proposals"] == [] and answer["errors"] == []
    said = warned(answer)
    assert ("Row 2 is a Kraken “transfer” with no subtype (an airdrop or a fork, a deal with Kraken's OTC desk, or a "
            "move to or from Kraken Futures): add it by hand if it moved bitcoin in or out of Kraken: left out.") in said
    assert "Rows 3 and 4 move coins between Kraken's own balances" in said  # a transfer that names its subtype


def test_a_kraken_ledger_without_its_subtype_column_says_to_export_it_whole(auth_client):
    """Without the subtype column (a ledger exported with fields left out),
    a move to staking can't be told from coins in or out: the owner is told
    to export every field, never to add a move within Kraken by hand."""
    header = '"txid","refid","time","type","aclass","asset","wallet","amount","fee","balance"\n'
    content = header + (
        '"LE1","TE1","2025-07-02 00:00:00","transfer","currency","XXBT","spot / main",-0.0010000000,0,0.009\n'
        '"LE2","TE1","2025-07-02 00:00:00","transfer","currency","XBT.S","spot / main",0.0010000000,0,0.001\n')
    answer = preview(auth_client, "kraken", content)
    assert answer["proposals"] == [] and answer["errors"] == []
    assert ("Rows 2 and 3 are Kraken “transfer” rows from a ledger exported without its subtype column, so a move "
            "within Kraken can't be told from coins in or out: export the ledger with all fields: left out."
            ) in warned(answer)


def test_a_row_of_a_dollar_word_that_carries_bitcoin_says_so(auth_client):
    """Strike's Withdrawal and Deposit are dollars, unless the row gives an
    amount of bitcoin (#813: an on-chain withdrawal, in two open-source
    parsers' notes): such a row isn't said to move dollars alone."""
    content = STRIKE_HEADER + (
        "a1,Jan 05 2025 14:00:00,Deposit,500.00,,,,,,,Bank deposit,,\n"
        "a2,Jan 06 2025 14:00:00,Withdrawal,,,-0.00100000,0.00000500,100000.00,,,On-chain,,\n")
    answer = preview(auth_client, "strike", content)
    assert answer["proposals"] == [] and answer["errors"] == []
    said = warned(answer)
    assert "Row 2 moves dollars, not bitcoin (“Deposit”): left out." in said
    assert ("Row 3 is “Withdrawal”, which this mapping reads as dollars, but its bitcoin column holds an amount: "
            "add it by hand if it moved bitcoin: left out.") in said


@pytest.mark.parametrize("mapping_id, words", [
    ("river", ("river.com", "Documents", "Statements", "Custom", "Bitcoin activity", "not Account activity")),
    ("coinbase", ("not Advanced", "Accounts", "Statements", "Transactions", "all assets, all transactions",
                  "CSV")),
    ("kraken", ("Documents", "Create export", "Ledgers", "first day to today", "all assets, types and fields",
                "ledgers.csv")),
    ("strike", ("Documents", "each past year's statement and this year's months", "Export as CSV",
                "Generate report")),
    ("swan", ("Export account data", "Deposits and purchases", "archived account")),
    ("swan-withdrawals", ("Export account data", "Withdrawals", "archived account")),
    ("cash-app", ("Documents", "Bitcoin", "Transactions CSV", "instead of them", "Export CSV")),
])
def test_each_mapping_says_how_to_download_its_file_today(auth_client, mapping_id, words):
    mappings = {m["id"]: m for m in auth_client.get("/api/import/exchange/mappings").json()["mappings"]}
    for word in words:
        assert word in mappings[mapping_id]["help"], (word, mappings[mapping_id]["help"])
