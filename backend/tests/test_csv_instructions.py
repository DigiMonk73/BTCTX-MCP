"""
The CSV import guide (backend/assets/csv_import_instructions.pdf, the "CSV
instructions" download) is its generator's output, and says what the import
takes. Its rules table said a deposit goes only to Wallet or Exchange BTC and
a withdrawal comes only from them; Bank and Exchange USD take both too
(#304).
"""

import contextlib
import importlib.util
import io
import shutil
from pathlib import Path

from pypdf import PdfReader

BACKEND = Path(__file__).resolve().parents[1]
SHIPPED = BACKEND / "assets" / "csv_import_instructions.pdf"


def text(path) -> str:
    return " ".join(" ".join(page.extract_text() for page in PdfReader(path).pages).split())


def test_the_shipped_guide_is_the_generators_output(tmp_path):
    """Regenerate it after changing the script: python backend/scripts/generate_csv_instructions_pdf.py.
    Run from a copy in a temp folder, so its PDF lands there."""
    copy = tmp_path / "scripts" / "generate_csv_instructions_pdf.py"
    copy.parent.mkdir()
    shutil.copyfile(BACKEND / "scripts" / "generate_csv_instructions_pdf.py", copy)
    spec = importlib.util.spec_from_file_location("csv_instructions", copy)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with contextlib.redirect_stdout(io.StringIO()):  # it prints where the PDF went
        made = module.generate_csv_instructions_pdf()
    assert text(made) == text(SHIPPED)


def test_a_deposit_or_withdrawal_takes_any_of_the_four_accounts():
    guide, four = text(SHIPPED), "Bank, Wallet, Exchange USD or Exchange BTC"
    assert f"Deposit External {four} Into Wallet or Exchange BTC: cost_basis_usd required" in guide
    assert f"Withdrawal {four} External From Wallet or Exchange BTC: purpose required" in guide
