"""
The standard disclaimer, worded the same everywhere (the owner's decision,
2026-10-10): the app, the report PDFs, the main README and the AI
connector's. The PDFs ask for "a tax professional", never an advisor or an
accountant. (The AI guide's line: mcp_server/tests/test_server.py.)
"""

import io
import re
from pathlib import Path

from pypdf import PdfReader

from backend.services.reports.complete_tax_report import generate_comprehensive_tax_report
from backend.services.reports.pdf_layout import DISCLAIMER, FOOTER_NOTE
from backend.tests.test_report_builders import REPORT

ROOT = Path(__file__).parents[2]


def flat(text: str) -> str:
    return " ".join(text.split())


def pdf_text(pdf: bytes) -> str:
    return flat(" ".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages))


def ts_constant(name: str) -> str:
    """A string constant of frontend/src/utils/disclaimer.ts, its pieces joined."""
    source = (ROOT / "frontend/src/utils/disclaimer.ts").read_text()
    body = re.search(rf"export const {name} =(.*?);", source, re.S).group(1)
    return "".join(re.findall(r'"([^"]*)"', body))


def test_the_disclaimer_is_worded_the_same_everywhere():
    assert ts_constant("DISCLAIMER") == DISCLAIMER
    # The one-wallet notice is the README's Important box, word for word
    readme = (ROOT / "README.md").read_text()
    box = re.search(r"> \[!IMPORTANT\]\n((?:> .*\n)+)", readme).group(1)
    assert ts_constant("ONE_WALLET_NOTICE") == flat(box.replace("> ", ""))
    for doc in ("README.md", "mcp_server/README.md"):
        assert DISCLAIMER in flat((ROOT / doc).read_text()), doc


def test_the_pdfs_carry_it(auth_client):
    auth_client.post("/api/transactions", json={
        "type": "Deposit", "timestamp": "2024-03-01T12:00:00Z", "from_account_id": 99, "to_account_id": 1,
        "amount": "100", "source": "N/A"})
    history = auth_client.get("/api/reports/simple_transaction_history", params={"year": 2024, "format": "pdf"})
    assert history.status_code == 200
    history_text = pdf_text(history.content)
    assert f"All amounts, fees, and cost data are shown as recorded in BitcoinTX. {DISCLAIMER}" in history_text
    report_text = pdf_text(generate_comprehensive_tax_report(REPORT))
    assert "may be used for tax purposes after you, or a tax professional, have checked it" in report_text
    for text in (history_text, report_text):
        assert FOOTER_NOTE in text
        assert not re.search(r"advisor|accountant", text)
