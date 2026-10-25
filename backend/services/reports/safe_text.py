"""
Ledger text on its way into the PDF and CSV reports.

- PDF: a ReportLab Paragraph reads its text as markup, and markup such as
  <img src="..."/> or <a href="..."> makes ReportLab open a file or fetch a
  URL while it builds the PDF. Everything the ledger supplies (a deposit's
  source, a fee currency, dates, amounts) goes through pdf_text(), which
  escapes it. As a second line, ReportLab opens no file and fetches
  nothing: it is told to trust no URL scheme and no host, and its readers of
  a file by name and of a URL (reportlab.lib.utils, which every image, font
  and URL that Paragraph markup names goes through) are replaced by a
  refusal, so markup that slipped through still reads nothing. The reports use no images,
  links or font files of their own (the standard fonts are built in). This
  module must be imported before ReportLab opens anything: until then its
  own readers are in place, and they open a file's path whatever the trust
  settings say.
- The built-in fonts draw Windows-1252 (WinAnsiEncoding) and nothing else:
  any other character, an emoji or a Cyrillic letter, would print as a
  black box. pdf_text() prints a "?" for each instead, and an account's
  name is refused when it holds one (prints_in_reports, the account
  service: #722, the owner's choice of a font file left unopened).
- CSV: a spreadsheet runs a cell that starts with = + - @ (or a tab or a
  line break) as a formula. csv_text() puts a ' in front of such a text
  value, and of one that starts with ' before such a text (#380). Numbers
  never go through it, so a loss stays -120.00. The files are written with
  the csv module, which quotes a cell holding a line break, so the text
  after one stays in its cell.

The IRS forms are filled by pypdf (pdf_form_filler.py), not ReportLab.
"""

from __future__ import annotations

import unicodedata
from xml.sax.saxutils import escape

from reportlab import rl_config
from reportlab.lib import utils as rl_utils

rl_config.trustedSchemes = []
rl_config.trustedHosts = []


def _read_nothing(*_args, **_kwargs):
    raise OSError("The reports open no file or URL.")


# Looked up by name each time ReportLab opens something, whoever imported
# its open_for_read: a file's path is opened before any trust setting is read.
rl_utils.open_for_read_by_name = _read_nothing
rl_utils.rlUrlRead = _read_nothing

FORMULA_START = ("=", "+", "-", "@", "\t", "\r", "\n")
# What the reports' built-in Helvetica draws: ReportLab's WinAnsiEncoding,
# whose glyphs are exactly Windows-1252's characters (control characters aside)
REPORT_ENCODING = "cp1252"


def pdf_text(value) -> str:
    """Text for a Paragraph, shown as written (never read as markup), with a
    "?" for each character the reports' font can't draw, never a black box."""
    text = "" if value is None else str(value)
    return escape(text.encode(REPORT_ENCODING, errors="replace").decode(REPORT_ENCODING))


def prints_in_reports(text: str) -> bool:
    """Whether the reports' font draws every character of `text`."""
    try:
        text.encode(REPORT_ENCODING)
    except UnicodeEncodeError:
        return False
    return True


def csv_text(value) -> str:
    """A text cell a spreadsheet won't run as a formula: also one that only
    looks plain, with spaces or a full-width sign before it. A text that
    already starts with the ' this puts before such a one gets another, so
    the CSV import, which takes one off, gives it back as it was (#380)."""
    text = "" if value is None else str(value)
    return "'" + text if _quoted(text) else text


def _quoted(text: str) -> bool:
    """Whether csv_text puts a ' before `text`: whether what follows the 's
    it starts with, if any, could run as a formula (a ' itself never does:
    NFKC keeps it, and it isn't a space), however many there are."""
    rest = text.lstrip("'")
    looks = unicodedata.normalize("NFKC", rest).lstrip()
    return rest.startswith(FORMULA_START) or looks.startswith(FORMULA_START[:4])
