"""
An account's name the tax report can print (#722; the owner's decision,
2026-10-25: limit names). The reports' only font, ReportLab's built-in
Helvetica, draws Windows-1252 (WinAnsiEncoding) and nothing else, and the
reports open no font file (safe_text.py). So adding or renaming a bank, a
wallet or an exchange refuses a name with a character outside it (emoji,
letters outside Western European alphabets), in plain words; accents, €,
an em dash and an apostrophe first (decision 23) stay allowed. A name saved
before (a 2.0 alpha allowed any) prints "?" for each such character, never
■, in the Complete Tax Report and the Transaction History.
"""

from decimal import Decimal
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

from backend.main import app
from backend.models.account import Account
from backend.models.exchange import Exchange
from backend.services.reports.safe_text import pdf_text
from backend.tests.conftest import default_login, stub_prices_at

UNPRINTABLE = ("A name can use letters, digits and punctuation the tax report can print: no emoji, and no "
               "letters outside Western European alphabets.")
EXTERNAL = 99
COLD, KRAKEN_USD, KRAKEN_BTC = 100, 101, 102


@pytest.fixture
def owner(fresh_app, monkeypatch) -> TestClient:
    stub_prices_at(monkeypatch, lambda when: Decimal("50000"))
    client = TestClient(app)
    assert client.post("/api/login", json=default_login()).status_code == 200
    client.Session = fresh_app
    return client


def add(client, kind: str, name: str):
    return client.post("/api/accounts/", json={"kind": kind, "name": name})


@pytest.mark.parametrize("kind, name", [
    ("wallet", "🔥 Cold storage"),
    ("wallet", "Кошелёк"),
    ("bank", "Ledger ✓"),
    ("wallet", "Cold ❄️"),  # an emoji's variation selector
    ("wallet", "\U0001f469‍\U0001f4bb wallet"),  # an emoji's joiner
    ("exchange", "Биржа"),
    ("exchange", "交易所"),
])
def test_a_name_the_report_cant_print_is_refused(owner, kind, name):
    r = add(owner, kind, name)
    assert r.status_code == 400
    assert r.json()["detail"] == UNPRINTABLE
    assert owner.get("/api/accounts/").json() == owner.get("/api/accounts/").json()  # nothing added
    assert [a["id"] for a in owner.get("/api/accounts/").json() if a["id"] >= 100] == []


@pytest.mark.parametrize("kind, name", [
    ("wallet", "Café Wallet €"),
    ("bank", "Müller's Bank — Zürich"),
    ("wallet", "'Savings"),  # an apostrophe first: decision 23
    ("exchange", "Ñandú Exchange"),
])
def test_a_name_it_can_print_is_kept(owner, kind, name):
    r = add(owner, kind, name)
    assert r.status_code == 201, r.text
    assert name in [a["exchange"] if a["kind"] == "exchange" else a["name"] for a in r.json()]


def test_a_rename_is_refused_too(owner):
    assert add(owner, "wallet", "Cold storage").status_code == 201
    assert add(owner, "exchange", "Kraken").status_code == 201
    for account_id, name in ((COLD, "🔥 Cold storage"), (2, "Ledger ✓"), (KRAKEN_BTC, "Биржа")):
        r = owner.put(f"/api/accounts/{account_id}", json={"name": name})
        assert r.status_code == 400, r.text
        assert r.json()["detail"] == UNPRINTABLE
    names = {a["id"]: a["name"] for a in owner.get("/api/accounts/").json()}
    assert (names[COLD], names[2], names[KRAKEN_USD], names[KRAKEN_BTC]) == (
        "Cold storage", "Wallet", "Kraken USD", "Kraken BTC")


def test_text_the_reports_cant_draw_is_a_question_mark():
    assert pdf_text("🔥 <b>Кот</b> — Café €") == "? &lt;b&gt;???&lt;/b&gt; — Café €"


def saved_unprintable(owner) -> None:
    """What a 2.0 alpha allowed: a wallet and an exchange named with an emoji
    and Cyrillic, saved before this rule, each holding coins in 2025."""
    assert add(owner, "wallet", "Cold storage").status_code == 201
    assert add(owner, "exchange", "Kraken").status_code == 201
    with owner.Session() as db:
        db.get(Account, COLD).name = "🔥 Cold storage"
        db.query(Exchange).filter(Exchange.name == "Kraken").one().name = "Биржа"
        db.get(Account, KRAKEN_USD).name = "Биржа USD"
        db.get(Account, KRAKEN_BTC).name = "Биржа BTC"
        db.commit()
    for to, when in ((COLD, "2025-02-01T12:00:00Z"), (KRAKEN_BTC, "2025-03-01T12:00:00Z")):
        r = owner.post("/api/transactions", json={
            "type": "Deposit", "timestamp": when, "from_account_id": EXTERNAL, "to_account_id": to,
            "amount": "0.1", "fee_amount": "0", "source": "MyBTC", "cost_basis_usd": "3000"})
        assert r.status_code == 200, r.text
    r = owner.post("/api/transactions", json={
        "type": "Sell", "timestamp": "2025-06-01T12:00:00Z", "from_account_id": KRAKEN_BTC,
        "to_account_id": KRAKEN_USD, "amount": "0.05", "fee_amount": "0", "proceeds_usd": "2500"})
    assert r.status_code == 200, r.text


def pdf_words(content: bytes) -> str:
    return " ".join("\n".join(p.extract_text() or "" for p in PdfReader(BytesIO(content)).pages).split())


@pytest.mark.parametrize("route", ["/api/reports/complete_tax_report?year=2025",
                                   "/api/reports/simple_transaction_history?year=2025&format=pdf"])
def test_a_name_saved_before_prints_a_question_mark_for_each_such_character(owner, route):
    saved_unprintable(owner)
    r = owner.get(route)
    assert r.status_code == 200, r.text
    words = pdf_words(r.content)
    assert "? Cold storage" in words
    assert "????? BTC" in words
    for drawn_as_a_box in ("🔥", "Биржа", "■"):
        assert drawn_as_a_box not in words


def test_the_csv_keeps_the_name_as_saved(owner):
    saved_unprintable(owner)
    r = owner.get("/api/reports/simple_transaction_history", params={"year": 2025, "format": "csv"})
    assert r.status_code == 200
    assert "🔥 Cold storage" in r.text and "Биржа BTC" in r.text
