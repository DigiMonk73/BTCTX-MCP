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


def test_a_deposit_or_withdrawal_takes_any_of_your_accounts():
    """By kind since 2.0 (5.5; #350): any bank, wallet or exchange account."""
    guide = text(SHIPPED)
    assert ("Deposit External Any of your accounts Into a bitcoin account (a wallet, or an exchange's BTC): "
            "cost_basis_usd required") in guide
    assert ("Withdrawal Any of your accounts External From a bitcoin account (a wallet, or an exchange's BTC): "
            "purpose required") in guide


def test_the_accounts_are_yours_by_their_names_in_settings():
    """5.11: a file names your accounts as Settings does; 1.x's names always
    mean the first bank, wallet and exchange; a hidden one imports with a
    warning."""
    guide = text(SHIPPED)
    assert "Your accounts Your banks, wallets and exchanges, each by its name in Settings (in any case)" in guide
    assert ("Bank, Wallet, Exchange USD and Exchange BTC always mean your first bank, wallet and exchange, "
            "as in BitcoinTX 1.x's files, whatever they are called now") in guide
    assert "Invalid account '...'\" Use one of your accounts by its name in Settings, or External" in guide
    assert "is hidden in Settings\" (a warning) The row imports" in guide


def test_the_rules_are_by_kind():
    guide = text(SHIPPED)
    assert ("Buy A bank, or an exchange's USD An exchange's BTC (the same exchange's, when paid from its USD)"
            in guide)
    assert "Sell An exchange's BTC The same exchange's USD" in guide
    assert ("Transfer One of your accounts Another of your accounts, in the same currency; or the same bitcoin "
            "account") in guide


def test_a_blank_fee_currency_is_the_accounts():
    """#350: as the save fills it in (#303), so a USD deposit's fee is USD."""
    assert ("Blank = USD for a Buy or Sell, else the currency of the account it's paid from (a deposit's: the "
            "account it goes into)") in text(SHIPPED)


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
    assert ("From a bank or an exchange's USD: any short text on one line, or blank; Spent, Gift, Donation or "
            "Lost isn't kept there") in guide
