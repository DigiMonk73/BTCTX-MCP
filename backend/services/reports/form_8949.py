# FILE: backend/services/reports/form_8949.py

import logging
from datetime import date, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Tuple, List, Dict, Literal
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.models import LotDisposal
from backend.models.transaction import Transaction
from backend.constants import ACCOUNT_EXCHANGE_BTC
from backend.services.tax_time import format_tax_date, get_tax_timezone, local_date, tax_year_bounds

logger = logging.getLogger(__name__)

##############################################################################
# 1) FORM 8949 ROW DEFINITION
##############################################################################
CURRENCY_PLACES = Decimal("0.01")

class Form8949Row:
    """
    Represents a single row on IRS Form 8949 (one line).
    (a) Description of property
    (b) Date acquired
    (c) Date sold
    (d) proceeds
    (e) cost
    (f) code (if any) or basis status
    (g) adjustment
    (h) gain/loss
    """
    def __init__(
        self,
        description: str,           # col (a)
        date_acquired: str,         # col (b)
        date_sold: str,             # col (c)
        proceeds: Decimal,          # col (d)
        cost: Decimal,              # col (e)
        gain_loss: Decimal,         # col (h)
        holding_period: Literal["SHORT", "LONG"],
        box: str  # checkbox letter for this row's Part (see _determine_box)
    ):
        self.description = description
        self.date_acquired = date_acquired
        self.date_sold = date_sold
        self.proceeds = Decimal(proceeds)
        self.cost = Decimal(cost)
        self.gain_loss = Decimal(gain_loss)
        self.holding_period = holding_period
        self.box = box
        # Columns (f) code and (g) adjustment stay blank: the app records no
        # adjustments. The box letter is NOT a column (f) code — it's the
        # checkbox at the top of the row's Part.

    def to_dict(self) -> Dict:
        """Convert to a dictionary with final, rounded decimal amounts."""
        return {
            "description": self.description,
            "date_acquired": self.date_acquired,
            "date_sold": self.date_sold,
            "proceeds": self._round(self.proceeds),
            "cost": self._round(self.cost),
            "gain_loss": self._round(self.gain_loss),
            "holding_period": self.holding_period,
            "box": self.box
        }

    @staticmethod
    def _round(amount) -> Decimal:
        return Decimal(amount).quantize(CURRENCY_PLACES, rounding=ROUND_HALF_UP)


##############################################################################
# 2) BUILDING 8949 DATA FROM DB
##############################################################################
# Compared lower-cased, as the ledger does: rows saved before input was
# normalized may say "gift" (they have $0 gain but used to print here).
# Gifts, donations and lost assets are reported separately, not as gains.
NON_TAXABLE_PURPOSES = ('gift', 'donation', 'lost')


def taxable_disposals(db: Session, start, end) -> List[LotDisposal]:
    """
    The lot disposals that go on Form 8949 for [start, end): sales, spends
    and network fees (a gift's fee too); not gifts, donations or lost coins. The complete tax
    report's capital-gains sections use the same list, so they can't
    disagree with the forms.
    """
    return (
        db.query(LotDisposal)
          .join(LotDisposal.transaction)
          .filter(Transaction.timestamp >= start, Transaction.timestamp < end)
          .filter(
              LotDisposal.is_fee
              | (Transaction.purpose.is_(None))
              | (~func.lower(Transaction.purpose).in_(NON_TAXABLE_PURPOSES))
          )
          .order_by(Transaction.timestamp, LotDisposal.id)
          .all()
    )


def build_form_8949_and_schedule_d(
    year: int,
    db: Session,
) -> Dict:
    """
    Gathers all LotDisposals for the given tax year, separates short vs. long,
    and returns a dict for your get_irs_reports route:

    {
      "short_term": [...row dicts...],
      "long_term":  [...row dicts...],
      "schedule_d": {
         "short_term": {"proceeds":..., "cost":..., "gain_loss":...},
         "long_term":  {"proceeds":..., "cost":..., "gain_loss":...}
      }
    }
    """
    tz = get_tax_timezone(db)
    start_date, end_date = tax_year_bounds(year, tz)

    disposals = taxable_disposals(db, start_date, end_date)

    rows_short: List[Form8949Row] = []
    rows_long: List[Form8949Row] = []

    for disp in disposals:
        broker_reported, basis_reported = _broker_reporting(disp, year, tz)
        box = _determine_box(disp.holding_period, basis_reported, year, broker_reported)

        # Format date_acquired
        if disp.lot and disp.lot.acquired_date:
            acquired_str = format_tax_date(disp.lot.acquired_date, tz)
        else:
            acquired_str = ""

        # date_sold
        sold_str = ""
        if disp.transaction and disp.transaction.timestamp:
            sold_str = format_tax_date(disp.transaction.timestamp, tz)

        # parse amounts
        proceeds_dec = Decimal(disp.proceeds_usd_for_that_portion or 0)
        cost_dec = Decimal(disp.disposal_basis_usd or 0)
        gain_dec = Decimal(disp.realized_gain_usd or 0)
        hp_str = (disp.holding_period or "SHORT").upper()

        row = Form8949Row(
            description=f"{disp.disposed_btc} BTC",
            date_acquired=acquired_str,
            date_sold=sold_str,
            proceeds=proceeds_dec,
            cost=cost_dec,
            gain_loss=gain_dec,
            holding_period=hp_str,
            box=box
        )

        if hp_str == "LONG":
            rows_long.append(row)
        else:
            rows_short.append(row)

    # Summaries for schedule D lines
    schedule_d = _build_schedule_d_data(rows_short, rows_long)

    return {
        "short_term": [r.to_dict() for r in rows_short],
        "long_term":  [r.to_dict() for r in rows_long],
        "schedule_d": schedule_d
    }


# Form 1099-DA: brokers report gross proceeds for digital-asset sales from
# 2025; basis only for "covered" assets — acquired on/after this date and held
# in the same broker account until sold (Treas. Reg. 1.6045-1, final 2024).
COVERED_DIGITAL_ASSET_START = date(2026, 1, 1)


def _broker_reporting(disp: LotDisposal, year: int, tz=timezone.utc) -> Tuple[bool, bool]:
    """
    (reported on a 1099-DA?, basis reported?) for one lot disposal.

    Only exchange Sells are broker-reported: that's what River (a US broker)
    puts on Form 1099-DA. Network-fee disposals and spends/withdrawals from
    self-custody aren't on any broker form. A Sell's basis is reported only
    for covered lots: bought on the exchange (a Buy into Exchange BTC) on or
    after 2026-01-01. BTC transferred in from elsewhere is noncovered — its
    lot is created by a Transfer, and transfers break the broker's basis chain.
    The acquisition date is taken in the tax timezone, matching column (b).
    """
    tx = disp.transaction
    if disp.is_fee:
        return False, False  # a network fee is never on a broker form
    if tx is not None and tx.broker_reporting:
        # The user recorded what the broker actually reported: that wins.
        return tx.broker_reporting != "none", tx.broker_reporting == "basis"
    if year < 2025 or tx is None or tx.type != "Sell" or tx.from_account_id != ACCOUNT_EXCHANGE_BTC:
        return False, False
    lot = disp.lot
    origin = lot.created_transaction if lot else None
    acquired = lot.acquired_date if lot else None
    covered = (
        origin is not None
        and origin.type == "Buy"
        and origin.to_account_id == ACCOUNT_EXCHANGE_BTC
        and acquired is not None
        and local_date(acquired, tz) >= COVERED_DIGITAL_ASSET_START
    )
    return True, covered


def _determine_box(holding_period: str, basis_reported: bool, year: int,
                   broker_reported: bool = False) -> str:
    """
    Which Form 8949 checkbox applies to a BTC disposal.

    Through 2024, crypto used the general boxes: A/D on a 1099-B with basis,
    B/E on a 1099-B without basis, C/F not on a 1099-B.
    From 2025 the form has digital-asset boxes and Box C/F exclude them:
      G / J  on a 1099-DA, basis reported
      H / K  on a 1099-DA, basis NOT reported (every 2025 exchange sale)
      I / L  not on a 1099-DA or 1099-B (self-custody spends, network fees)
    """
    long_term = holding_period.upper() == "LONG"
    if year >= 2025:
        if broker_reported:
            if basis_reported:
                return "J" if long_term else "G"
            return "K" if long_term else "H"
        return "L" if long_term else "I"
    if broker_reported:
        if basis_reported:
            return "D" if long_term else "A"
        return "E" if long_term else "B"
    return "F" if long_term else "C"


# Schedule D line for each Form 8949 box (printed on Schedule D itself)
SCHEDULE_D_LINE_FOR_BOX = {
    "A": "1b", "G": "1b", "B": "2", "H": "2", "C": "3", "I": "3",
    "D": "8b", "J": "8b", "E": "9", "K": "9", "F": "10", "L": "10",
}


def _build_schedule_d_data(short_rows: List[Form8949Row], long_rows: List[Form8949Row]) -> Dict[str, Dict[str, Decimal]]:
    """
    Schedule D totals: overall short/long, plus per line ("1b", "2", "3",
    "8b", "9", "10") keyed by the rows' Form 8949 box.
    """
    def totals(rows: List[Form8949Row]) -> Dict[str, Decimal]:
        return {
            "proceeds": Form8949Row._round(sum((r.proceeds for r in rows), Decimal("0"))),
            "cost": Form8949Row._round(sum((r.cost for r in rows), Decimal("0"))),
            "gain_loss": Form8949Row._round(sum((r.gain_loss for r in rows), Decimal("0"))),
        }

    by_line: Dict[str, List[Form8949Row]] = {}
    for r in short_rows + long_rows:
        by_line.setdefault(SCHEDULE_D_LINE_FOR_BOX[r.box], []).append(r)

    return {
        "short_term": totals(short_rows),
        "long_term": totals(long_rows),
        "lines": {line: totals(rows) for line, rows in by_line.items()},
    }


##############################################################################
# 3) YEAR-SPECIFIC FIELD CONFIGURATION
##############################################################################
def get_8949_field_config(year: int) -> Dict:
    """
    Return year-specific field configuration for Form 8949.

    The IRS changes field names between years. Key differences
    (verified against the official templates' form fields):
    - 2024: Table_Line1 on both pages, fields start at f1_3 (not zero-padded),
      14 rows per page (f1_3..f1_114 / f2_3..f2_114)
    - 2025: Table_Line1_Part1/Part2, row-1 fields zero-padded (f1_03..f1_10),
      11 rows per page (f1_03..f1_90 / f2_03..f2_90)

    Args:
        year: Tax year (e.g., 2024, 2025)

    Returns:
        Dictionary with field naming configuration
    """
    # Years whose templates were checked against this config (fields exist,
    # values land, box order matches the printed form). A new year folder
    # fails tests until it is added here — see docs/IRS_ANNUAL_FORM_UPDATE.md.
    if year >= 2025:
        return {
            "verified_years": [2025],
            "table_name_page1": "Table_Line1_Part1",
            "table_name_page2": "Table_Line1_Part2",
            "row1_zero_pad": True,  # f1_03, f1_04, ... f1_10
            "rows_per_page": 11,  # 2025 form shrank the table (was 14 rows)
            # Checkbox widgets c1_1[0..5] / c2_1[0..5], top to bottom; the
            # on-state of widget i is /(i+1). Verified against the PDF.
            "boxes_part1": ["A", "B", "C", "G", "H", "I"],
            "boxes_part2": ["D", "E", "F", "J", "K", "L"],
        }
    else:  # 2024 and earlier
        return {
            "verified_years": [2024],
            "table_name_page1": "Table_Line1",
            "table_name_page2": "Table_Line1",  # Same table name for both pages
            "row1_zero_pad": False,  # f1_3, f1_4, ...
            "rows_per_page": 14,
            "boxes_part1": ["A", "B", "C"],
            "boxes_part2": ["D", "E", "F"],
        }


def get_schedule_d_field_config(year: int) -> Dict[str, List[str]]:
    """
    Field names for each Schedule D line the app fills, in column order
    (d) proceeds, (e) cost, (g) adjustments, (h) gain or loss.
    Lines 1b/2/3 are in Part I, 8b/9/10 in Part II. Only difference between
    2024 and 2025: line 1b's field numbers are zero-padded in 2024.
    """
    line_1b = ["07", "08", "09", "10"] if year < 2025 else ["7", "8", "9", "10"]
    numbers = {
        "1b": line_1b,
        "2": ["11", "12", "13", "14"],
        "3": ["15", "16", "17", "18"],
        "8b": ["27", "28", "29", "30"],
        "9": ["31", "32", "33", "34"],
        "10": ["35", "36", "37", "38"],
    }
    config = {}
    for line, nums in numbers.items():
        part = "Table_PartI" if line in ("1b", "2", "3") else "Table_PartII"
        config[line] = [f"topmostSubform[0].Page1[0].{part}[0].Row{line}[0].f1_{n}[0]" for n in nums]
    return config


##############################################################################
# 4) FIELD-MAPPING HELPERS
##############################################################################
def checkbox_field_for_box(box: str, page: int, year: int) -> Tuple[str, str]:
    """
    (field name, on-state) of the Part I/II checkbox for `box`.
    The state is a PDF name like "/6" (fill_pdf_form sets it as the value).
    """
    config = get_8949_field_config(year)
    boxes = config["boxes_part1"] if page == 1 else config["boxes_part2"]
    if box not in boxes:
        raise ValueError(f"Box {box} is not in Part {'I' if page == 1 else 'II'} of the {year} Form 8949")
    i = boxes.index(box)
    return (
        f"topmostSubform[0].Page{page}[0].c{page}_1[{i}]",
        f"/{i + 1}",
    )


def map_8949_rows_to_field_data(rows: List[Form8949Row], page: int = 1, year: int = 2024) -> Dict[str, str]:
    """
    Fills the rows of ONE part of a Form 8949 sheet, using year-specific naming.

    The template only defines fields for its two physical pages:
      page=1 => Part I (short-term) table on Page1, f1_* fields
      page=2 => Part II (long-term) table on Page2, f2_* fields
    Overflow beyond one sheet is handled by the caller filling additional
    template copies — NOT by larger page numbers (f3_* fields don't exist).

    Field naming varies by year:
    - 2024: Table_Line1, f1_3, f1_4, ... (not zero-padded), 14 rows/page
    - 2025: Table_Line1_Part1/Part2, f1_03... (zero-padded row 1), 11 rows/page

    Args:
        rows: List of Form8949Row objects (max rows_per_page for the year)
        page: 1 = Part I (short-term), 2 = Part II (long-term)
        year: Tax year for field name selection

    Returns:
        Dictionary mapping field names to values
    """
    if page not in (1, 2):
        raise ValueError("page must be 1 (Part I) or 2 (Part II)")

    # Get year-specific configuration
    config = get_8949_field_config(year)

    if len(rows) > config["rows_per_page"]:
        raise ValueError(
            f"Cannot fit more than {config['rows_per_page']} rows on one {year} Form 8949 page"
        )

    table_name = config["table_name_page1"] if page == 1 else config["table_name_page2"]

    # Use page as the prefix number => f1_, f2_, ...
    prefix_num = page
    prefix = f"f{prefix_num}_"

    field_data: Dict[str, str] = {}

    # One box per Part per sheet: every row on the page must share it
    boxes = {r.box for r in rows}
    if len(boxes) > 1:
        raise ValueError(f"Rows for one Form 8949 page must share a box, got {sorted(boxes)}")
    if boxes:
        cb_name, cb_state = checkbox_field_for_box(boxes.pop(), page, year)
        field_data[cb_name] = cb_state

    for i, row_obj in enumerate(rows, start=1):
        # row1 => base=3, row2 => base=11, row3 => base=19, etc.
        base_index = 3 + (i - 1) * 8

        # Helper to format field number based on year/row
        def format_field_no(field_no: int, row_num: int) -> str:
            # In 2025, row 1 fields (3-10) are zero-padded, but row 2+ are not
            if config["row1_zero_pad"] and row_num == 1 and field_no < 10:
                return f"{field_no:02d}"
            return str(field_no)

        # Helper to build the actual PDF field name
        def field_name(row_i: int, field_no: int) -> str:
            formatted_no = format_field_no(field_no, row_i)
            return (
                f"topmostSubform[0].Page{prefix_num}[0].{table_name}[0].Row{row_i}[0].{prefix}{formatted_no}[0]"
            )

        # col (a) => offset=0 => description
        col_a = field_name(i, base_index + 0)
        field_data[col_a] = row_obj.description

        # col (b) => offset=1 => date acquired
        col_b = field_name(i, base_index + 1)
        field_data[col_b] = row_obj.date_acquired

        # col (c) => offset=2 => date sold
        col_c = field_name(i, base_index + 2)
        field_data[col_c] = row_obj.date_sold

        # col (d) => offset=3 => proceeds
        col_d = field_name(i, base_index + 3)
        field_data[col_d] = str(row_obj.proceeds)

        # col (e) => offset=4 => cost
        col_e = field_name(i, base_index + 4)
        field_data[col_e] = str(row_obj.cost)

        # col (f) => offset=5 => adjustment code(s) => none recorded
        col_f = field_name(i, base_index + 5)
        field_data[col_f] = ""

        # col (g) => offset=6 => adjustment => empty unless needed
        col_g = field_name(i, base_index + 6)
        field_data[col_g] = ""

        # col (h) => offset=7 => gain_loss
        col_h = field_name(i, base_index + 7)
        field_data[col_h] = str(row_obj.gain_loss)

    return field_data


def map_schedule_d_fields(schedule_d: Dict, year: int = 2024) -> Dict[str, str]:
    """
    Fill each Schedule D line that has Form 8949 rows: line 1b (A/G), 2 (B/H),
    3 (C/I), 8b (D/J), 9 (E/K), 10 (F/L). Adjustments (g) are blank.
    Accepts the older {"short_term", "long_term"} shape (treated as lines 3/10).
    """
    lines = schedule_d.get("lines")
    if lines is None:
        lines = {"3": schedule_d["short_term"], "10": schedule_d["long_term"]}
    config = get_schedule_d_field_config(year)
    fields: Dict[str, str] = {}
    for line, t in lines.items():
        proceeds, cost, adjustment, gain = config[line]
        fields[proceeds] = str(t["proceeds"])
        fields[cost] = str(t["cost"])
        fields[adjustment] = ""
        fields[gain] = str(t["gain_loss"])
    return fields
