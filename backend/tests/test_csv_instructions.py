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

import pytest
from pypdf import PdfReader

from backend.services.csv_import import CSV_COLUMNS, parse_csv_file

BACKEND = Path(__file__).resolve().parents[1]
SHIPPED = BACKEND / "assets" / "csv_import_instructions.pdf"
GENERATOR = BACKEND / "scripts" / "generate_csv_instructions_pdf.py"


def generator(path: Path = GENERATOR):
    spec = importlib.util.spec_from_file_location("csv_instructions", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def text(path) -> str:
    return " ".join(" ".join(page.extract_text() for page in PdfReader(path).pages).split())


def test_the_shipped_guide_is_the_generators_output(tmp_path):
    """Regenerate it after changing the script: python backend/scripts/generate_csv_instructions_pdf.py.
    Run from a copy in a temp folder, so its PDF lands there."""
    copy = tmp_path / "scripts" / "generate_csv_instructions_pdf.py"
    copy.parent.mkdir()
    shutil.copyfile(GENERATOR, copy)
    with contextlib.redirect_stdout(io.StringIO()):  # it prints where the PDF went
        made = generator(copy).generate_csv_instructions_pdf()
    assert text(made) == text(SHIPPED)


def test_a_deposit_or_withdrawal_takes_any_of_the_four_accounts():
    guide, four = text(SHIPPED), "Bank, Wallet, Exchange USD or Exchange BTC"
    assert f"Deposit External {four} Into Wallet or Exchange BTC: cost_basis_usd required" in guide
    assert f"Withdrawal {four} External From Wallet or Exchange BTC: purpose required" in guide


@pytest.mark.parametrize("title, row", generator().EXAMPLES)
def test_every_example_row_imports(title, row):
    """The Deposit and Withdrawal examples had 11 fields, not 12: "Income"
    was read as the fee currency and "Spent" as the source (#304's review).
    The examples follow the template's first 12 columns."""
    result = parse_csv_file((",".join(CSV_COLUMNS[:12]) + "\n" + row + "\n").encode())
    assert [e.message for e in result.errors] == [] and len(result.transactions) == 1


def test_a_deposit_or_withdrawal_isnt_bitcoin_only_anywhere():
    """The type table and the purpose column said bitcoin only too."""
    guide = text(SHIPPED)
    assert "Deposit Money or BTC coming in from outside" in guide
    assert "Withdrawal Money or BTC leaving" in guide
    # A dollar withdrawal keeps no bitcoin purpose (#449)
    assert ("From Bank or Exchange USD: any short text on one line, or blank; Spent, Gift, Donation or Lost "
            "isn't kept there") in guide
