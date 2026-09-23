# FILE: backend/routers/reports.py

from fastapi import APIRouter, Depends, Response, Query, HTTPException
from sqlalchemy.orm import Session
from typing import Dict, List
from io import BytesIO
from pypdf import PdfReader, PdfWriter
import os
import subprocess
import logging

logger = logging.getLogger(__name__)

# Get absolute paths to IRS templates (works regardless of working directory)
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.dirname(_THIS_DIR)
_ASSETS_DIR = os.path.join(_BACKEND_DIR, "assets", "irs_templates")

# Database & internal imports
from backend.database import get_db
from backend.services.reports.reporting_core import generate_report_data
from backend.services.reports.complete_tax_report import generate_comprehensive_tax_report
from backend.services.reports import transaction_history
from backend.services.reports.form_8949 import (
    build_form_8949_and_schedule_d,
    get_8949_field_config,
    map_8949_rows_to_field_data,
    map_schedule_d_fields,
    Form8949Row,
)
from itertools import zip_longest

# Import pdftk-based utilities (remove ghostscript references)
from backend.services.reports.pdftk_filler import fill_pdf_with_pdftk
from backend.services.reports.pdf_utils import flatten_pdf_with_pdftk
from backend.services.reports.pdftk_path import is_pdftk_available

reports_router = APIRouter()

@reports_router.get("/complete_tax_report")
def get_complete_tax_report(
    year: int,
    db: Session = Depends(get_db),
):
    """
    Generates a comprehensive tax report (PDF) that includes
    realized gains, income, fees, and balances.
    Uses ReportLab and doesn't need pdftk.
    """
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
    Generates a combined PDF for Form 8949 and Schedule D,
    using pdftk to remove XFA and flatten at each step.
    Then merges all partial PDFs into a final flattened file.

    Supports multiple tax years - templates are selected based on the year parameter.
    """
    # 0) Pre-flight checks
    _verify_pdftk_installed()
    _verify_templates_exist(year)

    # Get year-specific template paths
    path_form_8949 = get_template_path(year, "f8949.pdf")
    path_schedule_d = get_template_path(year, "f1040sd.pdf")

    try:
        # 1) Gather rows for Form 8949 + schedule totals
        report_data = build_form_8949_and_schedule_d(year, db)
        short_rows = [Form8949Row(**r) for r in report_data["short_term"]]
        long_rows = [Form8949Row(**r) for r in report_data["long_term"]]

        logger.info(f"Generating IRS reports for {year}: {len(short_rows)} short-term, {len(long_rows)} long-term disposals")

        partial_pdfs: List[bytes] = []

        # 2-3) Fill Form 8949 sheets. Each template copy is one physical sheet:
        # Page1 holds Part I (short-term) and Page2 holds Part II (long-term).
        # Chunk each term by the year's table capacity and pair chunks onto
        # shared sheets — overflow gets additional copies, never page-3+ field
        # names (those don't exist in the template; pdftk would drop the rows).
        # Each Form 8949 page carries exactly one checked box, so rows are
        # grouped by box before chunking (e.g. 1099-DA sales in Box H and
        # self-custody spends in Box I go on separate pages).
        rows_per_page = get_8949_field_config(year)["rows_per_page"]
        short_chunks = _chunks_by_box(short_rows, rows_per_page)
        long_chunks = _chunks_by_box(long_rows, rows_per_page)

        for short_chunk, long_chunk in zip_longest(short_chunks, long_chunks):
            field_data: Dict[str, str] = {}
            if short_chunk:
                field_data.update(map_8949_rows_to_field_data(short_chunk, page=1, year=year))
            if long_chunk:
                field_data.update(map_8949_rows_to_field_data(long_chunk, page=2, year=year))
            pdf_bytes = fill_pdf_with_pdftk(path_form_8949, field_data)
            partial_pdfs.append(pdf_bytes)

        # 4) Fill Schedule D totals using year-specific field names
        schedule_d_fields = map_schedule_d_fields(report_data["schedule_d"], year=year)
        filled_sd_bytes = fill_pdf_with_pdftk(path_schedule_d, schedule_d_fields)
        partial_pdfs.append(filled_sd_bytes)

        # 5) Merge partial PDFs in memory with pypdf
        merged_pdf = _merge_all_pdfs(partial_pdfs)

        # 6) Flatten the final merged PDF
        final_pdf = flatten_pdf_with_pdftk(merged_pdf)

        logger.info(f"Successfully generated IRS reports for {year} ({len(final_pdf)} bytes)")

        return Response(
            content=final_pdf,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename=\"IRSReports_{year}.pdf\"'}
        )

    except subprocess.CalledProcessError as e:
        logger.error(f"pdftk failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"PDF generation failed: pdftk error - {str(e)}"
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
    """
    Exports a raw list of transactions (CSV or PDF).
    Bypasses FIFO and gain/loss logic. This uses a custom
    ReportLab or CSV approach that doesn't need pdftk.
    """
    report_bytes = transaction_history.generate_transaction_history_report(db, year, format)

    file_ext = format.lower()
    content_type = "text/csv" if file_ext == "csv" else "application/pdf"
    file_name = f"SimpleTransactionHistory_{year}.{file_ext}"

    return Response(
        content=report_bytes,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename=\"{file_name}\"'}
    )


def _merge_all_pdfs(pdf_list: List[bytes]) -> bytes:
    """
    Merges multiple PDFs (in-memory bytes) into a single PDF with pypdf.
    """
    writer = PdfWriter()
    for pdf_data in pdf_list:
        reader = PdfReader(BytesIO(pdf_data))
        for page in reader.pages:
            writer.add_page(page)

    merged_stream = BytesIO()
    writer.write(merged_stream)
    return merged_stream.getvalue()


def _chunks_by_box(rows: List[Form8949Row], size: int) -> List[List[Form8949Row]]:
    """Split rows into page-sized chunks that never mix Form 8949 boxes."""
    by_box: Dict[str, List[Form8949Row]] = {}
    for row in rows:
        by_box.setdefault(row.box, []).append(row)
    return [
        group[i : i + size]
        for _, group in sorted(by_box.items())
        for i in range(0, len(group), size)
    ]


def get_supported_years() -> List[int]:
    """
    Return list of tax years with available IRS templates.
    Scans the irs_templates directory for year folders containing required PDFs.
    """
    years = []
    if not os.path.exists(_ASSETS_DIR):
        return years

    for item in os.listdir(_ASSETS_DIR):
        item_path = os.path.join(_ASSETS_DIR, item)
        if os.path.isdir(item_path) and item.isdigit():
            # Check that required templates exist
            has_8949 = os.path.exists(os.path.join(item_path, "f8949.pdf"))
            has_schedule_d = os.path.exists(os.path.join(item_path, "f1040sd.pdf"))
            if has_8949 and has_schedule_d:
                years.append(int(item))

    return sorted(years)


def get_template_path(year: int, form_name: str) -> str:
    """
    Get the template path for a specific tax year.

    Args:
        year: Tax year (e.g., 2024, 2025)
        form_name: Template filename (e.g., "f8949.pdf", "f1040sd.pdf")

    Returns:
        Absolute path to the template file

    Raises:
        HTTPException: If template doesn't exist for the requested year
    """
    template_path = os.path.join(_ASSETS_DIR, str(year), form_name)
    if not os.path.exists(template_path):
        supported = get_supported_years()
        raise HTTPException(
            status_code=400,
            detail=f"No {form_name} template available for tax year {year}. Supported years: {supported}"
        )
    return template_path


def _verify_pdftk_installed():
    """
    Verify pdftk is installed and accessible.
    Raises HTTPException with helpful message if not found.
    """
    if not is_pdftk_available():
        raise HTTPException(
            status_code=500,
            detail=(
                "pdftk is not installed or not in PATH. "
                "Install with: brew install pdftk-java (macOS) or apt-get install pdftk (Linux)"
            )
        )


def _verify_templates_exist(year: int):
    """
    Verify IRS PDF templates exist for the specified tax year.
    Raises HTTPException with helpful message if not found.
    """
    supported = get_supported_years()
    if year not in supported:
        raise HTTPException(
            status_code=400,
            detail=f"Tax year {year} not supported. Available years: {supported}"
        )