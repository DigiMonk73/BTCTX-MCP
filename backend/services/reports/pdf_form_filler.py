"""
backend/services/reports/pdf_form_filler.py

Fill and flatten IRS AcroForm PDFs in pure Python with pypdf.

Replaces the external pdftk (Java) dependency: no system install on macOS,
Docker or StartOS. Output was compared page-by-page against pdftk for the
2024 and 2025 Form 8949 and Schedule D (Schedule D pixel-identical; 8949 text
sits within a pixel or two in the description column).

  fill_pdf_form(template, {field_name: value})         -> flattened PDF bytes
  fill_pdf_form(template, fields, flatten=False)       -> fillable PDF (tests)

Values: text fields take strings; checkboxes take their on-state name as a
string starting with "/" (e.g. "/6"), see form_8949.checkbox_field_for_box.
"""

from __future__ import annotations

import io
import logging
from typing import Dict

from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, NameObject

logger = logging.getLogger(__name__)


def fill_pdf_form(template_path: str, field_data: Dict[str, str], flatten: bool = True) -> bytes:
    """
    Fill `template_path` with `field_data`.

    Unknown field names are an error (pdftk used to drop them silently,
    which produced blank forms): the IRS renaming a field must fail loudly.
    With flatten=True every field — filled or empty — is burned into the page
    and the form is removed, so the result can't be edited.
    """
    writer = PdfWriter(clone_from=template_path)
    acroform = writer._root_object["/AcroForm"]
    # IRS PDFs also carry an XFA form; viewers that honor XFA would ignore
    # our AcroForm values, so drop it (pdftk's "drop_xfa").
    if "/XFA" in acroform:
        del acroform[NameObject("/XFA")]

    template_fields = PdfReader(template_path).get_fields() or {}
    unknown = sorted(set(field_data) - set(template_fields))
    if unknown:
        raise ValueError(
            f"{len(unknown)} field(s) not in {template_path}, e.g. {unknown[:3]} — "
            "the IRS template changed; see docs/IRS_ANNUAL_FORM_UPDATE.md"
        )

    values: Dict[str, str] = {}
    for name, field in template_fields.items():
        kind = field.get("/FT")
        if kind == "/Btn":
            values[name] = field_data.get(name, "/Off")
        elif kind == "/Tx":
            values[name] = field_data.get(name, "")

    if not flatten:
        values = {k: v for k, v in values.items() if k in field_data}

    for page in writer.pages:
        writer.update_page_form_field_values(page, values, auto_regenerate=False, flatten=flatten)
        if flatten and "/Annots" in page:
            kept = [a for a in page["/Annots"] if a.get_object().get("/Subtype") != "/Widget"]
            if kept:
                page[NameObject("/Annots")] = ArrayObject(kept)
            else:
                del page[NameObject("/Annots")]

    if flatten:
        del writer._root_object[NameObject("/AcroForm")]
    else:
        writer.set_need_appearances_writer(True)

    buf = io.BytesIO()
    writer.write(buf)
    logger.debug("Filled %s: %d fields (flatten=%s)", template_path, len(field_data), flatten)
    return buf.getvalue()
