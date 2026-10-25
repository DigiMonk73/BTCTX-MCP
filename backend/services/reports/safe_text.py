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
- The built-in fonts draw what Helvetica's encoding (Windows-1252) holds,
  then what Symbol's and ZapfDingbats' hold (unaccented Greek, arrows,
  some signs); any other character, most emoji or a Cyrillic letter,
  would print as a black box. pdf_text() prints a "?" for each instead,
  by ReportLab's own rule, so what printed before prints the same. An
  account's name keeps to Windows-1252, Western European letters
  (in_report_font, the account service): #722, the owner's choice, with
  no font file opened.
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
from functools import cache
from xml.sax.saxutils import escape

from reportlab import rl_config
from reportlab.lib import utils as rl_utils
from reportlab.pdfbase import pdfmetrics

rl_config.trustedSchemes = []
rl_config.trustedHosts = []


def _read_nothing(*_args, **_kwargs):
    raise OSError("The reports open no file or URL.")


# Looked up by name each time ReportLab opens something, whoever imported
# its open_for_read: a file's path is opened before any trust setting is read.
rl_utils.open_for_read_by_name = _read_nothing
rl_utils.rlUrlRead = _read_nothing

FORMULA_START = ("=", "+", "-", "@", "\t", "\r", "\n")
# The reports' font (pdf_layout.FONT): its encoding, Windows-1252, holds
# the Western European letters an account's name keeps to (#722)
REPORT_FONT, NAME_ENCODING = "Helvetica", "cp1252"
# A Paragraph draws these as spaces
SPACES = ("\t", "\n", "\r")
# Variation selectors: they only choose how the character before them looks
VARIATION_SELECTORS = ((0xFE00, 0xFE0F), (0xE0100, 0xE01EF))


def pdf_text(value) -> str:
    """Text for a Paragraph, shown as written (never read as markup), with a
    "?" for each character the reports' fonts can't draw, never a black box:
    composed first (an accent typed apart joins its letter), and without what
    nothing shows (a joiner, a variation selector), so it's one "?" for each
    character seen."""
    text = unicodedata.normalize("NFC", "" if value is None else str(value))
    return escape("".join(c if _drawn(c) else "?" for c in text if not _unseen(c)))


def in_report_font(text: str) -> bool:
    """Whether every character of `text` is one the reports' own font draws
    (Windows-1252): what an account's name may hold (#722). The fonts it
    falls back to draw some signs and unaccented Greek, but not the letters
    around them, so a name keeps to Western European alphabets."""
    try:
        text.encode(NAME_ENCODING)
    except UnicodeEncodeError:
        return False
    return True


@cache
def _drawn(c: str) -> bool:
    """ReportLab's own rule (pdfmetrics.unicode2T1): the first of the font
    and the fonts it falls back to whose encoding holds `c` draws it, a
    black box when that encoding has no glyph there (a control character)."""
    if c in SPACES:
        return True
    font = pdfmetrics.getFont(REPORT_FONT)
    for each in (font, *font.substitutionFonts):
        try:
            code = c.encode(each.encName)
        except UnicodeEncodeError:
            continue
        vector = pdfmetrics.getEncoding(each.encName).vector
        return all(vector[b] is not None for b in code)
    return False


def _unseen(c: str) -> bool:
    """A format character but the soft hyphen (which prints a hyphen), or a variation selector."""
    return (unicodedata.category(c) == "Cf" and c != "\u00ad") or any(
        low <= ord(c) <= high for low, high in VARIATION_SELECTORS)


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
