"""
The printed IRS forms read back, for the tests of what BitcoinTX prints: the
text a flattened Form 8949 or Schedule D shows in each field, found where it
is drawn on the page. So the tests check the PDF a preparer gets, not the
values handed to the filler.

The layout comes from the year's template itself: a table row's fields by
their name (RowN), its columns left to right by position, the checkboxes
top to bottom. Only what the IRS prints is written in here: the boxes'
letters in their printed order and each box's Schedule D line. Nothing
uses form_8949.py's field maps, so a wrong map shows up as a wrong
read-back.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader
from pypdf.generic import ContentStream

# The checkboxes of each Part, top to bottom, as printed on the IRS forms
BOXES_UNTIL_2024 = {1: "ABC", 2: "DEF"}
BOXES_FROM_2025 = {1: "ABCGHI", 2: "DEFJKL"}
# The Schedule D line each box's totals go on (printed on Schedule D)
SCHEDULE_D_LINE = {
    "A": "1b", "G": "1b", "B": "2", "H": "2", "C": "3", "I": "3",
    "D": "8b", "J": "8b", "E": "9", "K": "9", "F": "10", "L": "10",
}
ROW_COLUMNS = "abcdefgh"
LINE2_COLUMNS = "defgh"
SCHEDULE_D_COLUMNS = "degh"
# Enough opening text to tell the template pages apart (all differ well before it)
SIGNATURE_LENGTH = 200


@dataclass(frozen=True)
class Widget:
    name: str  # the field's full name, e.g. topmostSubform[0].Page1[0].f1_01[0]
    x: float   # where its appearance is drawn: the lower-left of its /Rect
    y: float
    text: bool  # a text field (/Tx); otherwise a checkbox


@dataclass(frozen=True)
class TemplatePage:
    form: str        # "f8949" or "f1040sd"
    signature: str   # the page's opening text, which a printed copy starts with too
    widgets: tuple[Widget, ...]


@dataclass
class PrintedPage:
    template: TemplatePage
    values: dict[str, str]  # field name -> the text drawn in it ("" when nothing)

    def value(self, widget: Widget) -> str:
        return self.values.get(widget.name, "")


@dataclass
class Form8949Part:
    """One printed Form 8949 page: Part I (short-term) or Part II (long-term)."""
    part: int
    boxes: str               # the letters of the checkboxes drawn checked
    rows: list[dict[str, str]]   # filled rows, column letter -> text, in table order
    empty_rows_between: bool  # a blank row before a filled one
    line2: dict[str, str]


def template_pages(path: Path, form: str) -> list[TemplatePage]:
    """Every page of an IRS template that has fields, with their names and
    positions (a draft's cover sheet has none, and is never printed)."""
    reader = PdfReader(str(path))
    pages = []
    for page in reader.pages:
        widgets = []
        for annot in page.get("/Annots") or []:
            annot = annot.get_object()
            if annot.get("/Subtype") != "/Widget":
                continue
            x, y = (float(v) for v in annot["/Rect"][:2])
            widgets.append(Widget(_full_name(annot), round(x, 2), round(y, 2), _field_type(annot) == "/Tx"))
        if widgets:
            pages.append(TemplatePage(form, _signature(page), tuple(widgets)))
    return pages


def read_printed(pdf: bytes, templates: list[TemplatePage]) -> list[PrintedPage]:
    """Each page of a printed (flattened) PDF: which template page it is and
    what each field shows. A page that is no template page fails."""
    reader = PdfReader(BytesIO(pdf))
    printed = []
    for number, page in enumerate(reader.pages, start=1):
        signature = _signature(page)
        template = next((t for t in templates if t.signature and signature.startswith(t.signature)), None)
        assert template is not None, f"page {number} is no page of the IRS templates: {signature[:80]!r}"
        values = _drawn_fields(page, reader, template)
        # A flattened page draws every text field once (an empty one too):
        # one not found would read as blank and pass the checks for blanks.
        missing = [w.name for w in template.widgets if w.text and w.name not in values]
        assert not missing, f"page {number}: {len(missing)} text field(s) not found where drawn, e.g. {missing[:2]}"
        printed.append(PrintedPage(template, values))
    return printed


def form_8949_part(page: PrintedPage, year: int) -> Form8949Part:
    """A printed Form 8949 page read as the IRS lays it out."""
    widgets = page.template.widgets
    part = 1 if any(".Page1[0]." in w.name for w in widgets) else 2
    letters = (BOXES_FROM_2025 if year >= 2025 else BOXES_UNTIL_2024)[part]
    checkboxes = sorted((w for w in widgets if re.search(r"\.c\d_1\[\d+\]$", w.name)), key=lambda w: -w.y)
    assert len(checkboxes) == len(letters), f"{len(checkboxes)} checkboxes on Part {part} of {year}"
    boxes = "".join(letter for letter, w in zip(letters, checkboxes) if page.value(w))

    rows, gap, seen_blank = [], False, False
    for cells in _table_rows(widgets):
        texts = {col: page.value(w) for col, w in zip(ROW_COLUMNS, cells)}
        if any(texts.values()):
            gap = gap or seen_blank
            rows.append(texts)
        else:
            seen_blank = True
    return Form8949Part(part, boxes, rows, gap, _line2(page))


def schedule_d_lines(pages: list[PrintedPage]) -> dict[str, dict[str, str]]:
    """Schedule D's table lines (1a, 1b, 2, ... 10): column letter -> text."""
    lines = {}
    for page in pages:
        by_line: dict[str, list[Widget]] = {}
        for w in page.template.widgets:
            m = re.search(r"\.Table_Part[I]+\[0\]\.Row(\w+)\[0\]\.", w.name)
            if m:
                by_line.setdefault(m.group(1), []).append(w)
        for line, cells in by_line.items():
            cells.sort(key=lambda w: w.x)
            assert len(cells) == len(SCHEDULE_D_COLUMNS), f"Schedule D line {line} has {len(cells)} fields"
            lines[line] = {col: page.value(w) for col, w in zip(SCHEDULE_D_COLUMNS, cells)}
    return lines


def other_schedule_d_values(pages: list[PrintedPage]) -> dict[str, str]:
    """Every Schedule D field outside lines 1a-10's table that shows something."""
    return {name: text for page in pages for name, text in page.values.items()
            if text and ".Table_Part" not in name}


def amount(text: str) -> Decimal:
    """A printed dollar amount: 1234.56, -9.74 or (9.74)."""
    text = text.replace(",", "")
    if text.startswith("(") and text.endswith(")"):
        return -Decimal(text[1:-1])
    return Decimal(text)


def report_boxes(report_text: str) -> dict[str, dict[str, str]]:
    """The Complete Tax Report's "Form 8949 and Schedule D" table: box ->
    its Schedule D line, rows, proceeds, cost basis and gain (loss), as printed."""
    start = report_text.index("Form 8949 and Schedule D\n")
    end = report_text.index("Each box is its own Form 8949 page", start)
    lines = report_text[start:end].split("\n")
    boxes, box, figures = {}, None, []
    for line in lines[1:]:
        if re.fullmatch(r"[A-L]", line):
            box, figures = line, []
        elif box and line.startswith(" "):
            figures.append(line.strip())
            if len(figures) == 5:
                boxes[box] = dict(zip(("line", "rows", "proceeds", "cost", "gain"), figures))
                box = None
    return boxes


def _field_type(annot) -> str | None:
    """/FT, which a widget may inherit from its parent field."""
    node = annot
    while node is not None:
        if "/FT" in node:
            return str(node["/FT"])
        node = node.get("/Parent")
        node = node.get_object() if node is not None else None
    return None


def _full_name(annot) -> str:
    parts = []
    node = annot
    while node is not None:
        if "/T" in node:
            parts.append(str(node["/T"]))
        node = node.get("/Parent")
        node = node.get_object() if node is not None else None
    return ".".join(reversed(parts))


def _signature(page) -> str:
    return " ".join((page.extract_text() or "").split())[:SIGNATURE_LENGTH]


def _drawn_fields(page, reader: PdfReader, template: TemplatePage) -> dict[str, str]:
    """Field name -> text, for each form XObject the page draws at a field's
    position (`q <cm> /Name Do Q`, how a flattened field is drawn)."""
    at = {(w.x, w.y): w.name for w in template.widgets}
    xobjects = page["/Resources"].get("/XObject") or {}
    values: dict[str, str] = {}
    translation = None
    for operands, operator in ContentStream(page.get_contents(), reader).operations:
        if operator == b"cm":
            translation = (round(float(operands[4]), 2), round(float(operands[5]), 2))
        elif operator == b"Do" and translation in at and operands[0] in xobjects:
            name = at[translation]
            assert name not in values, f"{name} drawn twice"
            values[name] = _xobject_text(xobjects[operands[0]].get_object(), reader)
        elif operator == b"Q":
            translation = None
    return values


def _xobject_text(xobject, reader: PdfReader) -> str:
    parts = []
    for operands, operator in ContentStream(xobject, reader).operations:
        if operator in (b"Tj", b"'", b'"'):
            parts.append(_decoded(operands[-1]))
        elif operator == b"TJ":
            parts.extend(_decoded(item) for item in operands[0] if isinstance(item, (str, bytes)))
    return "".join(parts).strip()


def _decoded(value) -> str:
    return value.decode("latin-1") if isinstance(value, bytes) else str(value)


def _table_rows(widgets: tuple[Widget, ...]) -> list[list[Widget]]:
    """The table's rows in order (Row1, Row2...), each row's cells left to right."""
    rows: dict[int, list[Widget]] = {}
    for w in widgets:
        m = re.search(r"\.Table_Line1\w*\[0\]\.Row(\d+)\[0\]\.", w.name)
        if m:
            rows.setdefault(int(m.group(1)), []).append(w)
    for number, cells in rows.items():
        assert len(cells) == len(ROW_COLUMNS), f"row {number} has {len(cells)} fields"
    return [sorted(cells, key=lambda w: w.x) for _, cells in sorted(rows.items())]


def _line2(page: PrintedPage) -> dict[str, str]:
    """Line 2, "Totals": the page's own fields (not in the table) lowest on it."""
    loose = [w for w in page.template.widgets
             if re.search(r"\.Page\d\[0\]\.f\d_\d+\[0\]$", w.name)]
    bottom = min(w.y for w in loose)
    cells = sorted((w for w in loose if abs(w.y - bottom) < 1), key=lambda w: w.x)
    assert len(cells) == len(LINE2_COLUMNS), f"line 2 has {len(cells)} fields"
    return {col: page.value(w) for col, w in zip(LINE2_COLUMNS, cells)}
