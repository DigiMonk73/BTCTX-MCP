"""
What the ReportLab reports (the complete tax report and the transaction
history) share: one look. A palette, the paragraph styles, the tables
(header row, light row shading, right-aligned figures, a totals row, the
header repeated on every page a table runs onto) and the page frame
(running header, "Page X of Y" footer). Built-in Helvetica only: the
reports use no font files, images or links (safe_text.py).
"""

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Table, TableStyle

INK = colors.HexColor("#1A1D21")
MUTED = colors.HexColor("#5F6B7A")
RULE = colors.HexColor("#D5DAE1")
HEADER_FILL = colors.HexColor("#EEF1F5")
SHADE = colors.HexColor("#F8F9FB")
ACCENT = colors.HexColor("#F7931A")  # Bitcoin orange
ACCENT_SOFT = colors.HexColor("#FEF4E8")

FONT, BOLD = "Helvetica", "Helvetica-Bold"


class ReportStyles:
    """A report's paragraph styles; each document gets its own set."""

    def __init__(self):
        def style(name, size, leading, font=FONT, color=INK, align=TA_LEFT, **extra):
            return ParagraphStyle(name=name, fontName=font, fontSize=size, leading=leading,
                                  textColor=color, alignment=align, **extra)

        self.kicker = style("Kicker", 9, 12, BOLD, ACCENT)
        self.title = style("Title", 30, 34, BOLD)
        self.subtitle = style("Subtitle", 11.5, 16, color=MUTED)
        # A heading stays with its intro; a long table after them still starts
        # on the same page (a report reserves room with CondPageBreak)
        self.heading = style("Heading", 15, 19, BOLD, spaceBefore=4, spaceAfter=2, keepWithNext=1)
        self.subheading = style("Subheading", 10.5, 14, BOLD, spaceBefore=10, spaceAfter=5)
        self.normal = style("Body", 9, 13)
        self.intro = style("Intro", 9, 13, color=MUTED, spaceAfter=8)
        self.bullet = style("Bullet", 9, 13, leftIndent=12, bulletIndent=0, spaceAfter=5)
        self.note = style("Note", 7.5, 10, color=MUTED, spaceBefore=4)
        self.label = style("Label", 7, 9, BOLD, MUTED)
        self.metric = style("Metric", 15, 18, BOLD)
        self.metric_detail = style("MetricDetail", 7.5, 10, color=MUTED)
        # Table cells: small, and long words wrap instead of overflowing.
        self.cell = style("Cell", 8, 10, wordWrap="CJK")
        self.cell_bold = style("CellBold", 8, 10, BOLD, wordWrap="CJK")
        self.number = style("Number", 8, 10, align=TA_RIGHT, wordWrap="CJK")
        self.number_bold = style("NumberBold", 8, 10, BOLD, align=TA_RIGHT, wordWrap="CJK")
        self.head = style("Head", 7, 9, BOLD, MUTED, wordWrap="CJK")
        self.head_number = style("HeadNumber", 7, 9, BOLD, MUTED, align=TA_RIGHT, wordWrap="CJK")


def data_table(rows: list, widths: list, total: bool = False) -> Table:
    """
    A report table: `rows[0]` is the header, `widths` are in inches. Light
    shading on every other row, rules between rows, no vertical lines; a
    `total` last row is set off by a rule above it. The header repeats on
    every page the table runs onto.
    """
    table = Table(rows, colWidths=[width * inch for width in widths], repeatRows=1)
    body_end = len(rows) - (2 if total else 1)
    commands = [
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_FILL),
        ("LINEBELOW", (0, 0), (-1, 0), 0.75, RULE),
        ("LINEBELOW", (0, 1), (-1, -1), 0.25, RULE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("FONT", (0, 0), (-1, -1), FONT, 8),
        ("TEXTCOLOR", (0, 0), (-1, -1), INK),
    ]
    commands += [("BACKGROUND", (0, r), (-1, r), SHADE) for r in range(2, body_end + 1, 2)]
    if total:
        commands += [("LINEABOVE", (0, -1), (-1, -1), 0.9, INK), ("LINEBELOW", (0, -1), (-1, -1), 0.9, INK)]
    table.setStyle(TableStyle(commands))
    return table


def numbered_canvas(footer_right: str = "Page {page} of {pages}"):
    """
    A canvas class that writes `footer_right` ("Page 2 of 7") at the foot of
    every page once the number of pages is known.
    """
    class NumberedCanvas(Canvas):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._pages: list[dict] = []

        def showPage(self):
            self._pages.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            for state in self._pages:
                self.__dict__.update(state)
                self.setFont(FONT, 7.5)
                self.setFillColor(MUTED)
                self.drawRightString(self._pagesize[0] - 0.75 * inch, 0.5 * inch,
                                     footer_right.format(page=self._pageNumber, pages=len(self._pages)))
                super().showPage()
            super().save()

    return NumberedCanvas


def draw_running_header(canvas: Canvas, title: str) -> None:
    """The wordmark, `title` on the right, and a rule under them."""
    width, height = canvas._pagesize
    top = height - 0.55 * inch
    canvas.setFillColor(ACCENT)
    canvas.rect(0.75 * inch, top - 1, 6, 6, stroke=0, fill=1)
    canvas.setFillColor(INK)
    canvas.setFont(BOLD, 8)
    canvas.drawString(0.75 * inch + 10, top, "BitcoinTX")
    canvas.setFillColor(MUTED)
    canvas.setFont(FONT, 8)
    canvas.drawRightString(width - 0.75 * inch, top, title)
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.5)
    canvas.line(0.75 * inch, top - 6, width - 0.75 * inch, top - 6)


def draw_footer_note(canvas: Canvas, note: str) -> None:
    """`note` at the foot of the page, left, above a hairline."""
    width = canvas._pagesize[0]
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.5)
    canvas.line(0.75 * inch, 0.68 * inch, width - 0.75 * inch, 0.68 * inch)
    canvas.setFillColor(MUTED)
    canvas.setFont(FONT, 7.5)
    canvas.drawString(0.75 * inch, 0.5 * inch, note)
