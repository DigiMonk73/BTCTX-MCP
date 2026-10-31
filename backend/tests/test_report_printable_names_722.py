"""
An account's name the tax report can print (#722; the owner's decision,
2026-10-25: limit names). The reports open no font file (safe_text.py):
ReportLab's built-in Helvetica draws Windows-1252 (WinAnsiEncoding), then
Symbol's and ZapfDingbats' characters (unaccented Greek, arrows, some
signs), and a black box for anything else. Adding or renaming a bank, a
wallet or an exchange refuses a name outside Windows-1252 (emoji, letters
outside Western European alphabets), in plain words; accents, €, an em
dash and an apostrophe first (decision 23) stay allowed. A name saved
before (a 2.0 alpha allowed any) prints "?" for each character the fonts
can't draw, never ■, in the Complete Tax Report and the Transaction
History; what they draw prints as before.
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
COLD, KRAKEN_USD, KRAKEN_BTC, SECOND = 100, 101, 102, 103


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


@pytest.mark.parametrize("text, printed", [
    ("🔥 <b>Кот</b> — Café €", "? &lt;b&gt;???&lt;/b&gt; — Café €"),
    # what Symbol and ZapfDingbats draw prints as it always has
    ("→ ✓ α ≥ ❄ ★", "→ ✓ α ≥ ❄ ★"),
    ("Ταμείο ✓ → Wallet", "Ταμε?ο ✓ → Wallet"),
    # a control character has no glyph: a black box until now
    ("a\x01b\x7fc\td", "a?b?c\td"),
    # an accent typed apart joins its letter; what nothing shows isn't a "?"
    ("Cafe\u0301 Zu\u0308rich", "Café Zürich"),
    ("Cold \u2744\ufe0f", "Cold \u2744"),
    ("\U0001f469\u200d\U0001f4bb wallet", "?? wallet"),
    ("soft\u00adhyphen", "soft\u00adhyphen"),
    # a space of any kind is a gap, as it always was (a Mac's "10:00\u202fAM")
    ("Coffee\u202fshop a\x0bb Gift\u3000Mom", "Coffee\u202fshop a\x0bb Gift\u3000Mom"),
    # signs Symbol draws stay as they are, whatever else is in the text
    ("x \u2329y\u232a", "x \u2329y\u232a"),
    ("Кот \u2329y\u232a", "??? \u2329y\u232a"),
])
def test_text_the_reports_cant_draw_is_a_question_mark(text, printed):
    assert pdf_text(text) == printed


def saved_unprintable(owner) -> None:
    """What a 2.0 alpha allowed: wallets and an exchange named with an emoji,
    Cyrillic, and Greek with signs, saved before this rule, each holding
    coins in 2025."""
    assert add(owner, "wallet", "Cold storage").status_code == 201
    assert add(owner, "exchange", "Kraken").status_code == 201
    assert add(owner, "wallet", "Second").status_code == 201
    with owner.Session() as db:
        db.get(Account, SECOND).name = "Ταμείο ✓ → Wallet"
        db.get(Account, COLD).name = "🔥 Cold storage"
        db.query(Exchange).filter(Exchange.name == "Kraken").one().name = "Биржа"
        db.get(Account, KRAKEN_USD).name = "Биржа USD"
        db.get(Account, KRAKEN_BTC).name = "Биржа BTC"
        db.commit()
    for to, when in ((COLD, "2025-02-01T12:00:00Z"), (KRAKEN_BTC, "2025-03-01T12:00:00Z"),
                     (SECOND, "2025-04-01T12:00:00Z")):
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
    assert "Ταμε?ο ✓ → Wallet" in words  # what the fonts draw prints as typed
    for drawn_as_a_box in ("🔥", "Биржа", "■"):
        assert drawn_as_a_box not in words


def test_the_csv_keeps_the_name_as_saved(owner):
    saved_unprintable(owner)
    r = owner.get("/api/reports/simple_transaction_history", params={"year": 2025, "format": "csv"})
    assert r.status_code == 200
    assert "🔥 Cold storage" in r.text and "Биржа BTC" in r.text
