"""
A fresh ledger with two more exchanges, Kraken and Overseas, made through
the account API, and the gate opened for them as B7a will open it
(conftest's gate_open): card B4's tests (#349) save Buys, Sells and
Transfers on them through the transactions API, and read Form 8949, the
complete tax report and Ledger Review. Every row the ledger saves is kept
in the shape scripts/independent_figures.py reads, so each case is also
worked out by that second calculation, from the rules, never the app's code.
"""

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.models.account import Account
from backend.models.exchange import Exchange
from backend.services.reports.form_8949 import build_form_8949_and_schedule_d
from backend.services.reports.reporting_core import generate_report_data
from backend.services.review import build_review
from backend.tests.conftest import default_login
from backend.tests.independent_calc import independent_figures, ledger_tx

BANK, WALLET, EXCHANGE_USD, EXCHANGE_BTC, EXTERNAL = 1, 2, 3, 4, 99
# The ids the account API gives a fresh ledger: Kraken, then Overseas
KRAKEN_USD, KRAKEN_BTC, OVERSEAS_USD, OVERSEAS_BTC = 100, 101, 102, 103
FORM_COLUMNS = ("box", "date_acquired", "date_sold", "proceeds", "cost")


class Ledger:
    def __init__(self, client: TestClient, Session):
        self.client, self.Session = client, Session
        self.rows: list[dict] = []
        self.tax_timezone = "UTC"

    def set_tax_timezone(self, zone: str) -> None:
        r = self.client.put("/api/settings/tax-timezone", json={"timezone": zone, "chosen": True})
        assert r.status_code == 200, r.text
        self.tax_timezone = zone

    def save(self, kind, when, src, dst, amount, **more) -> dict:
        """One transaction, as the independent calculation reads it too."""
        row = ledger_tx(kind, f"{when}T12:00:00Z" if "T" not in when else when, src, dst, amount, **more)
        r = self.client.post("/api/transactions", json=row)
        assert r.status_code == 200, r.text
        self.rows.append(row)
        return r.json()

    def switch(self, exchange: str, on: bool) -> None:
        """An exchange's "This exchange sends me a Form 1099-DA" (B6c and B7b set it on screen)."""
        with self.Session() as db:
            db.query(Exchange).filter(Exchange.name == exchange).update({"sends_1099da": on})
            db.commit()

    def form_8949(self, year: int) -> list[tuple]:
        with self.Session() as db:
            forms = build_form_8949_and_schedule_d(year, db)
        return sorted(tuple(str(r[c]) for c in FORM_COLUMNS) for r in forms["short_term"] + forms["long_term"])

    def boxes(self, year: int) -> list[str]:
        return sorted(row[0] for row in self.form_8949(year))

    def independent_form_8949(self, year: int) -> list[tuple]:
        """The same rows by the second calculation, in the ledger's accounts and switches."""
        independent = independent_figures()
        replayed = independent.replay(self.rows, accounts=independent.read_accounts({"accounts": self.accounts()}),
                                      tax_timezone=self.tax_timezone)
        return sorted(tuple(r[c] for c in FORM_COLUMNS) for r in independent.year_figures(replayed, year)["form_8949"])

    def accounts(self) -> list[dict]:
        with self.Session() as db:
            switches = dict(db.query(Exchange.id, Exchange.sends_1099da))
            return [{"id": a.id, "name": a.name, "currency": a.currency, "kind": a.kind,
                     **({"exchange_id": a.exchange_id, "sends_1099da": switches[a.exchange_id]}
                        if a.exchange_id is not None else {})}
                    for a in db.query(Account) if a.kind != "fee" and a.id != EXTERNAL]

    def report(self, year: int) -> dict:
        with self.Session() as db:
            return generate_report_data(db, year)

    def review(self) -> dict:
        with self.Session() as db:
            return build_review(db)


@pytest.fixture
def ledger(gate_open, fresh_app) -> Ledger:
    client = TestClient(app)
    assert client.post("/api/login", json=default_login()).status_code == 200
    for name in ("Kraken", "Overseas"):
        r = client.post("/api/accounts/", json={"kind": "exchange", "name": name})
        assert r.status_code == 201, r.text
    assert [a["id"] for a in r.json()] == [OVERSEAS_USD, OVERSEAS_BTC]
    return Ledger(client, fresh_app)
