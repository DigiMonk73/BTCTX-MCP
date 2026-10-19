"""
The standard disclaimer, worded the same everywhere (the owner's decision,
2026-10-10): the app, the report PDFs, the main README and the AI
connector's. The PDFs ask for "a tax professional", never an advisor or an
accountant. (The AI guide's line: mcp_server/tests/test_server.py.)
"""

import io
import re
import subprocess
from pathlib import Path

from pypdf import PdfReader

from backend.services.reports.complete_tax_report import generate_comprehensive_tax_report
from backend.services.reports.pdf_layout import DISCLAIMER, FOOTER_NOTE
from backend.tests.test_report_builders import REPORT
from backend.tests.test_test_files import needs_a_checkout

ROOT = Path(__file__).parents[2]

# More than one wallet, exchange, bank or account is "multiple", never
# "several" (the owner, 2026-10-18), wherever the phrase is split: across
# lines, a quote's "> ", a comment's "#" or "//", joined strings or bold.
SEVERAL_ACCOUNTS = re.compile(r"\bseveral (?:[\w-]+ ){0,2}(?:wallets|exchanges|accounts|banks|brokers)\b", re.I)
BETWEEN_WORDS = re.compile(r"[\s>#/*\"'+]+")
TEXT = (".md", ".py", ".ts", ".tsx", ".json", ".yml", ".yaml", ".html", ".txt")


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
    box = re.search(r"> \[!IMPORTANT\]\n((?:>.*\n)+)", readme).group(1)
    assert ts_constant("ONE_WALLET_NOTICE") == flat(re.sub(r"^> ?", "", box, flags=re.M))
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
    assert "prepared from your own records: check it with a tax professional before you file." in report_text
    for text in (history_text, report_text):
        assert FOOTER_NOTE in text
        assert not re.search(r"advisor|accountant", text)


def unreleased(path: str, text: str) -> str:
    """What of a tracked file isn't released yet: released text keeps its
    words (the CHANGELOG's versions, and 1.2.9's release notes until the
    next bump rewrites them)."""
    if path == "docs/CHANGELOG.md":
        return text.split("\n## [v", 1)[0]
    if path == "startos/startos/versions/current.ts" and "version: '1.2.9:0'" in text:
        return ""
    return text


@needs_a_checkout
def test_more_than_one_account_is_multiple_never_several():
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    found = [f"{path}: {hit.group(0)}" for path in tracked.splitlines() if path.endswith(TEXT)
             for hit in SEVERAL_ACCOUNTS.finditer(BETWEEN_WORDS.sub(" ", unreleased(path, (ROOT / path).read_text())))]
    assert not found, found
