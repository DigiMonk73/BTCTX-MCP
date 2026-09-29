"""
Ledger text on its way into the PDF and CSV reports.

- PDF: a ReportLab Paragraph reads its text as markup, and markup such as
  <img src="..."/> or <a href="..."> makes ReportLab open a file or fetch a
  URL while it builds the PDF. Everything the ledger supplies (a deposit's
  source, a fee currency, dates, amounts) goes through pdf_text(), which
  escapes it. As a second line, ReportLab is told to trust no URL scheme and
  no host, so markup that slipped through still fetches nothing; the reports
  use no images, links or font files of their own. This module must be
  imported before ReportLab opens anything: it reads these settings once.
- CSV: a spreadsheet runs a cell that starts with = + - @ (or a tab or CR)
  as a formula. csv_text() puts a ' in front of such a text value. Numbers
  never go through it, so a loss stays -120.00.

The IRS forms are filled by pypdf (pdf_form_filler.py), not ReportLab.
"""

from __future__ import annotations

from xml.sax.saxutils import escape

from reportlab import rl_config

rl_config.trustedSchemes = []
rl_config.trustedHosts = []

FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def pdf_text(value) -> str:
    """Text for a Paragraph, shown as written (never read as markup)."""
    return escape("" if value is None else str(value))


def csv_text(value) -> str:
    """A text cell a spreadsheet won't run as a formula."""
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(FORMULA_START) else text
