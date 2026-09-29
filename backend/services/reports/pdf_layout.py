"""
What the ReportLab reports (the complete tax report and the transaction
history) share: their paragraph styles and their grid tables.
"""

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Table, TableStyle


class ReportStyles:
    """A report's paragraph styles; each document gets its own set."""

    def __init__(self):
        sample = getSampleStyleSheet()
        self.title = sample["Title"]
        self.heading = ParagraphStyle(
            name="Heading1Left", parent=sample["Heading1"], alignment=0, spaceBefore=12, spaceAfter=8,
        )
        self.normal = sample["Normal"]
        # Table cells: small, and long words wrap instead of overflowing.
        self.cell = ParagraphStyle(name="Wrapped", parent=self.normal, fontSize=8, leading=10, wordWrap="CJK")
        self.number = ParagraphStyle(name="RightAligned", parent=self.cell, alignment=2)


def grid_table(rows: list, widths: list, align: str = "RIGHT", columns: tuple = (0, -1)) -> Table:
    """A table with a grey grid and a shaded header row. `widths` are in
    inches; `align` applies to the `columns` range (first, last)."""
    table = Table(rows, colWidths=[width * inch for width in widths])
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("ALIGN", (columns[0], 0), (columns[1], -1), align),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
    ]))
    return table
