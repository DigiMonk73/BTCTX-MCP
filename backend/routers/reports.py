"""
Report downloads: the IRS Form 8949 and Schedule D (the year's templates,
filled with pypdf), the complete tax report and the transaction history.
"""

from fastapi import APIRouter, Depends, Response, Query, HTTPException
from sqlalchemy.orm import Session
from io import BytesIO
from pypdf import PdfReader, PdfWriter
import os
import logging

logger = logging.getLogger(__name__)

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.dirname(_THIS_DIR)
_ASSETS_DIR = os.path.join(_BACKEND_DIR, "assets", "irs_templates")

from backend.database import get_db
from backend.services.reports.reporting_core import generate_report_data
from backend.services.reports.complete_tax_report import generate_comprehensive_tax_report
from backend.services.reports import draft_forms, transaction_history
from backend.services.reports.form_8949 import (
    build_form_8949_and_schedule_d,
    get_8949_field_config,
    map_8949_rows_to_field_data,
    map_schedule_d_fields,
    Form8949Row,
)
from itertools import zip_longest
from backend.services.reports.pdf_form_filler import fill_pdf_form

reports_router = APIRouter()


@reports_router.get("/years")
def get_report_years(db: Session = Depends(get_db)) -> dict[str, list[int]]:
    """
    The years the Reports page offers: `ledger_years` from the first
    transaction's tax year (in the tax timezone) to this year, newest first,
    and `form_years`, the years this version has IRS Form 8949 / Schedule D
    templates for: `draft_years` of them only as the IRS's drafts, on a test
    install that has them (services/reports/draft_forms.py).
    """
    from datetime import datetime, timezone

    from sqlalchemy import func

    from backend.models.transaction import Transaction
    from backend.services.tax_time import get_tax_timezone, local_date

    tz = get_tax_timezone(db)
    this_year = datetime.now(timezone.utc).astimezone(tz).year
    first = db.query(func.min(Transaction.timestamp)).scalar()
    first_year = min(local_date(first, tz).year, this_year) if first else this_year
    bundled = get_supported_years()
    drafts = draft_forms.draft_years(bundled)
    return {
        "ledger_years": list(range(this_year, first_year - 1, -1)),
        "form_years": sorted(bundled + drafts),
        "draft_years": drafts,
    }


@reports_router.get("/complete_tax_report")
def get_complete_tax_report(
    year: int,
    db: Session = Depends(get_db),
):
    """The complete tax report PDF of one tax year."""
    report_dict = generate_report_data(db, year)
    pdf_bytes = generate_comprehensive_tax_report(report_dict)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="CompleteTaxReport_{year}.pdf"'}
    )


@reports_router.get("/irs_reports")
def get_irs_reports(
    year: int,
    db: Session = Depends(get_db),
):
    """
    Form 8949 and Schedule D of one tax year in one PDF, from that year's
    templates: each sheet is filled and flattened with pypdf (XFA removed),
    then all are merged. A draft year's sheets leave out the IRS's cover page.
    """
    _verify_templates_exist(year)
    path_form_8949 = get_template_path(year, "f8949.pdf")
    path_schedule_d = get_template_path(year, "f1040sd.pdf")
    draft = year not in get_supported_years()
    first_8949 = draft_forms.first_form_page(path_form_8949) if draft else 0
    first_schedule_d = draft_forms.first_form_page(path_schedule_d) if draft else 0

    try:
        report_data = build_form_8949_and_schedule_d(year, db)
        short_rows = [Form8949Row(**r) for r in report_data["short_term"]]
        long_rows = [Form8949Row(**r) for r in report_data["long_term"]]

        logger.debug(f"Generating IRS reports for {year}: {len(short_rows)} short-term, {len(long_rows)} long-term disposals")

        partial_pdfs: list[tuple[bytes, int]] = []  # (sheet, its first page to keep)

        # Each template copy is one physical sheet:
        # Page1 holds Part I (short-term) and Page2 holds Part II (long-term).
        # Chunk each term by the year's table capacity and pair chunks onto
        # shared sheets — overflow gets additional copies, never page-3+ field
        # names (those don't exist in the template).
        # Each Form 8949 page carries exactly one checked box, so rows are
        # grouped by box before chunking (e.g. 1099-DA sales in Box H and
        # self-custody spends in Box I go on separate pages).
        rows_per_page = get_8949_field_config(year)["rows_per_page"]
        short_chunks = _chunks_by_box(short_rows, rows_per_page)
        long_chunks = _chunks_by_box(long_rows, rows_per_page)

        for short_chunk, long_chunk in zip_longest(short_chunks, long_chunks):
            field_data: dict[str, str] = {}
            if short_chunk:
                field_data.update(map_8949_rows_to_field_data(short_chunk, page=1, year=year))
            if long_chunk:
                field_data.update(map_8949_rows_to_field_data(long_chunk, page=2, year=year))
            pdf_bytes = fill_pdf_form(path_form_8949, field_data)
            partial_pdfs.append((pdf_bytes, first_8949))

        schedule_d_fields = map_schedule_d_fields(report_data["schedule_d"], year=year)
        filled_sd_bytes = fill_pdf_form(path_schedule_d, schedule_d_fields)
        partial_pdfs.append((filled_sd_bytes, first_schedule_d))

        final_pdf = _merge_all_pdfs(partial_pdfs)  # sheets are already flattened

        logger.info(f"Successfully generated IRS reports for {year} ({len(final_pdf)} bytes)")

        return Response(
            content=final_pdf,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename=\"IRSReports_{year}.pdf\"'}
        )

    except Exception as e:
        logger.error(f"IRS report generation failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"IRS report generation failed: {str(e)}"
        )


@reports_router.get("/simple_transaction_history")
def get_simple_transaction_history(
    year: int,
    format: str = Query("csv", pattern="^(csv|pdf)$"),
    db: Session = Depends(get_db),
):
    """The tax year's transactions as a CSV or PDF list."""
    report_bytes = transaction_history.generate_transaction_history_report(db, year, format)

    file_ext = format.lower()
    content_type = "text/csv" if file_ext == "csv" else "application/pdf"
    file_name = f"SimpleTransactionHistory_{year}.{file_ext}"

    return Response(
        content=report_bytes,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename=\"{file_name}\"'}
    )


def _merge_all_pdfs(pdf_list: list[tuple[bytes, int]]) -> bytes:
    """The PDFs' pages, in order, as one PDF; each from its given first page."""
    writer = PdfWriter()
    for pdf_data, first_page in pdf_list:
        reader = PdfReader(BytesIO(pdf_data))
        for page in reader.pages[first_page:]:
            writer.add_page(page)

    merged_stream = BytesIO()
    writer.write(merged_stream)
    return merged_stream.getvalue()


def _chunks_by_box(rows: list[Form8949Row], size: int) -> list[list[Form8949Row]]:
    """Split rows into page-sized chunks that never mix Form 8949 boxes."""
    by_box: dict[str, list[Form8949Row]] = {}
    for row in rows:
        by_box.setdefault(row.box, []).append(row)
    return [
        group[i : i + size]
        for _, group in sorted(by_box.items())
        for i in range(0, len(group), size)
    ]


def get_supported_years() -> list[int]:
    """The tax years with both IRS templates in backend/assets/irs_templates/."""
    years = []
    if not os.path.exists(_ASSETS_DIR):
        return years

    for item in os.listdir(_ASSETS_DIR):
        item_path = os.path.join(_ASSETS_DIR, item)
        if os.path.isdir(item_path) and item.isdigit():
            has_8949 = os.path.exists(os.path.join(item_path, "f8949.pdf"))
            has_schedule_d = os.path.exists(os.path.join(item_path, "f1040sd.pdf"))
            if has_8949 and has_schedule_d:
                years.append(int(item))

    return sorted(years)


def get_form_years() -> list[int]:
    """The bundled years, and a newer year's IRS drafts on a test install."""
    bundled = get_supported_years()
    return sorted(bundled + draft_forms.draft_years(bundled))


def get_template_path(year: int, form_name: str) -> str:
    """The path of a year's template ("f8949.pdf", "f1040sd.pdf"): the
    bundled one, else a test install's draft; or 400."""
    template_path = os.path.join(_ASSETS_DIR, str(year), form_name)
    if not os.path.exists(template_path) and year in draft_forms.draft_years(get_supported_years()):
        template_path = draft_forms.template_path(year, form_name)
    if not os.path.exists(template_path):
        supported = get_form_years()
        raise HTTPException(
            status_code=400,
            detail=f"No {form_name} template available for tax year {year}. Supported years: {supported}"
        )
    return template_path


def _verify_templates_exist(year: int):
    """400 unless the year has IRS templates."""
    supported = get_form_years()
    if year not in supported:
        raise HTTPException(
            status_code=400,
            detail=f"Tax year {year} not supported. Available years: {supported}"
        )