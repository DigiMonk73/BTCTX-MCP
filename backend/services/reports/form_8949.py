# FILE: backend/services/reports/form_8949.py

import logging
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Tuple, List, Dict, Literal, Optional
from sqlalchemy.orm import Session

from backend.models import LotDisposal
from backend.models.transaction import Transaction

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
def build_form_8949_and_schedule_d(
    year: int,
    db: Session,
    basis_reported_flags: Optional[Dict[int, bool]] = None
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
    start_date = datetime(year, 1, 1, tzinfo=timezone.utc)
    end_date = datetime(year + 1, 1, 1, tzinfo=timezone.utc)

    # Non-taxable disposal purposes that should NOT appear on Form 8949
    # Gifts, donations, and lost assets are reported separately, not as capital gains/losses
    NON_TAXABLE_PURPOSES = ('Gift', 'Donation', 'Lost')

    disposals = (
        db.query(LotDisposal)
          .join(LotDisposal.transaction)
          .filter(Transaction.timestamp >= start_date, Transaction.timestamp < end_date)
          .filter(
              # Exclude non-taxable disposals (gifts, donations, lost assets)
              # These have a purpose field set; taxable disposals (Sell, Spent, Transfer fees) don't
              (Transaction.purpose.is_(None)) | (~Transaction.purpose.in_(NON_TAXABLE_PURPOSES))
          )
          .all()
    )

    rows_short: List[Form8949Row] = []
    rows_long: List[Form8949Row] = []

    for disp in disposals:
        # If you do basis_reported_flags => A or C (short), D or F (long)
        is_basis_reported = False
        if basis_reported_flags and disp.id in basis_reported_flags:
            is_basis_reported = basis_reported_flags[disp.id]

        # Decide box letter
        box = _determine_box(disp.holding_period, is_basis_reported, year)

        # Format date_acquired
        if disp.lot and disp.lot.acquired_date:
            acquired_str = disp.lot.acquired_date.strftime("%m/%d/%Y")
        else:
            acquired_str = ""

        # date_sold
        sold_str = ""
        if disp.transaction and disp.transaction.timestamp:
            sold_str = disp.transaction.timestamp.strftime("%m/%d/%Y")

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


def _determine_box(holding_period: str, basis_reported: bool, year: int) -> str:
    """
    Which Form 8949 checkbox applies to a BTC disposal.

    Through 2024, crypto used the general boxes: A/C (short), D/F (long).
    From 2025 the form has digital-asset boxes, and Box C/F explicitly
    exclude digital assets:
      G / J  digital assets on a 1099-DA with basis reported
      I / L  digital assets NOT reported on a 1099-DA or 1099-B
    Self-custody BTC with no broker form is I (short) / L (long).
    """
    long_term = holding_period.upper() == "LONG"
    if year >= 2025:
        if basis_reported:
            return "J" if long_term else "G"
        return "L" if long_term else "I"
    if basis_reported:
        return "D" if long_term else "A"
    return "F" if long_term else "C"


def _build_schedule_d_data(short_rows: List[Form8949Row], long_rows: List[Form8949Row]) -> Dict[str, Dict[str, Decimal]]:
    """
    Summarize short vs. long for schedule D lines 1b & 8b.
    """
    st_proceeds = sum(r.proceeds for r in short_rows)
    st_cost = sum(r.cost for r in short_rows)
    st_gain = sum(r.gain_loss for r in short_rows)

    lt_proceeds = sum(r.proceeds for r in long_rows)
    lt_cost = sum(r.cost for r in long_rows)
    lt_gain = sum(r.gain_loss for r in long_rows)

    return {
        "short_term": {
            "proceeds": Form8949Row._round(st_proceeds),
            "cost": Form8949Row._round(st_cost),
            "gain_loss": Form8949Row._round(st_gain),
        },
        "long_term": {
            "proceeds": Form8949Row._round(lt_proceeds),
            "cost": Form8949Row._round(lt_cost),
            "gain_loss": Form8949Row._round(lt_gain),
        }
    }


##############################################################################
# 3) YEAR-SPECIFIC FIELD CONFIGURATION
##############################################################################
def get_8949_field_config(year: int) -> Dict:
    """
    Return year-specific field configuration for Form 8949.

    The IRS changes field names between years. Key differences
    (verified against pdftk dump_data_fields of the official templates):
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
            "row1_base_index": 3,  # Row 1 starts at field index 3
            "row1_zero_pad": True,  # f1_03, f1_04, ... f1_10
            "row2_plus_zero_pad": False,  # f1_11, f1_12, ... (no padding after row 1)
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
            "row1_base_index": 3,
            "row1_zero_pad": False,  # f1_3, f1_4, ...
            "row2_plus_zero_pad": False,
            "rows_per_page": 14,
            "boxes_part1": ["A", "B", "C"],
            "boxes_part2": ["D", "E", "F"],
        }


def get_schedule_d_field_config(year: int) -> Dict[str, str]:
    """
    Return year-specific field names for Schedule D.

    IMPORTANT: Self-tracked crypto transactions (not reported on 1099-B/1099-DA) use:
    - Line 3 (Box C or Box I) for short-term
    - Line 10 (Box F or Box L) for long-term

    Key differences by year:
    - 2024: Row3 uses f1_15-f1_18, Row10 uses f1_35-f1_38
    - 2025+: Same field numbers, different structure confirmed

    Args:
        year: Tax year (e.g., 2024, 2025)

    Returns:
        Dictionary mapping field purposes to actual field names
    """
    if year >= 2025:
        return {
            # Short-term (line 3 - Box C/I: not reported on 1099)
            "short_proceeds": "topmostSubform[0].Page1[0].Table_PartI[0].Row3[0].f1_15[0]",
            "short_cost": "topmostSubform[0].Page1[0].Table_PartI[0].Row3[0].f1_16[0]",
            "short_adjustment": "topmostSubform[0].Page1[0].Table_PartI[0].Row3[0].f1_17[0]",
            "short_gain_loss": "topmostSubform[0].Page1[0].Table_PartI[0].Row3[0].f1_18[0]",
            # Long-term (line 10 - Box F/L: not reported on 1099)
            "long_proceeds": "topmostSubform[0].Page1[0].Table_PartII[0].Row10[0].f1_35[0]",
            "long_cost": "topmostSubform[0].Page1[0].Table_PartII[0].Row10[0].f1_36[0]",
            "long_adjustment": "topmostSubform[0].Page1[0].Table_PartII[0].Row10[0].f1_37[0]",
            "long_gain_loss": "topmostSubform[0].Page1[0].Table_PartII[0].Row10[0].f1_38[0]",
        }
    else:  # 2024 and earlier
        return {
            # Short-term (line 3 - Box C: not reported on 1099)
            "short_proceeds": "topmostSubform[0].Page1[0].Table_PartI[0].Row3[0].f1_15[0]",
            "short_cost": "topmostSubform[0].Page1[0].Table_PartI[0].Row3[0].f1_16[0]",
            "short_adjustment": "topmostSubform[0].Page1[0].Table_PartI[0].Row3[0].f1_17[0]",
            "short_gain_loss": "topmostSubform[0].Page1[0].Table_PartI[0].Row3[0].f1_18[0]",
            # Long-term (line 10 - Box F: not reported on 1099)
            "long_proceeds": "topmostSubform[0].Page1[0].Table_PartII[0].Row10[0].f1_35[0]",
            "long_cost": "topmostSubform[0].Page1[0].Table_PartII[0].Row10[0].f1_36[0]",
            "long_adjustment": "topmostSubform[0].Page1[0].Table_PartII[0].Row10[0].f1_37[0]",
            "long_gain_loss": "topmostSubform[0].Page1[0].Table_PartII[0].Row10[0].f1_38[0]",
        }


##############################################################################
# 4) FIELD-MAPPING HELPERS
##############################################################################
def checkbox_field_for_box(box: str, page: int, year: int) -> Tuple[str, str]:
    """
    (field name, on-state) of the Part I/II checkbox for `box`.
    The state is a PDF name like "/6"; generate_fdf writes it as a name.
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
    template copies — NOT by larger page numbers (f3_* fields don't exist;
    pdftk would silently drop them).

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


def map_schedule_d_fields(schedule_d: Dict[str, Dict[str, Decimal]], year: int = 2024) -> Dict[str, str]:
    """
    Puts the short-term totals on Schedule D line 3 and long-term totals on
    line 10 (Form 8949 boxes C/F through 2024, I/L from 2025 — transactions
    not reported on a 1099), using the year's field names.

    Args:
        schedule_d: Dictionary with short_term and long_term totals
        year: Tax year for field name selection

    Returns:
        Dictionary mapping field names to values
    """
    short_data = schedule_d["short_term"]
    long_data = schedule_d["long_term"]

    # Get year-specific field names
    config = get_schedule_d_field_config(year)

    return {
        # Short-term (line 1b)
        config["short_proceeds"]: str(short_data["proceeds"]),
        config["short_cost"]: str(short_data["cost"]),
        config["short_adjustment"]: "",  # adjustments
        config["short_gain_loss"]: str(short_data["gain_loss"]),
        # Long-term (line 8b)
        config["long_proceeds"]: str(long_data["proceeds"]),
        config["long_cost"]: str(long_data["cost"]),
        config["long_adjustment"]: "",
        config["long_gain_loss"]: str(long_data["gain_loss"]),
    }
