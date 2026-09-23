# FILE: backend/services/reports/pdftk_filler.py

import subprocess
import tempfile
import os
import logging

from backend.services.reports.pdftk_path import get_pdftk_path

logger = logging.getLogger(__name__)

def generate_fdf(field_data: dict) -> str:
    """
    Generates an FDF (Forms Data Format) text from a Python dictionary of
    { fieldName: value }. Each key in field_data is the PDF form field name,
    and its value is the string to insert.

    We'll escape parentheses "()" with backslashes. If you have more complex
    or non-ASCII data, consider more robust escaping.
    """
    lines = [
        "%FDF-1.2",
        "1 0 obj << ",
        "/FDF << /Fields ["
    ]

    for key, value in field_data.items():
        escaped_key = key.replace("(", r"\(").replace(")", r"\)")
        if value.startswith("/"):
            # Checkbox/radio on-state: must be a PDF name, not a string
            lines.append(f"<< /T ({escaped_key}) /V {value} >>")
            continue
        escaped_value = value.replace("(", r"\(").replace(")", r"\)")
        lines.append(f"<< /T ({escaped_key}) /V ({escaped_value}) >>")

    lines.append("] >> ")
    lines.append(">>")
    lines.append("endobj")
    lines.append("trailer")
    lines.append("<< /Root 1 0 R >>")
    lines.append("%%EOF")

    return "\n".join(lines)


def fill_pdf_with_pdftk(template_path: str, field_data: dict) -> bytes:
    """
    Fills a PDF form using pdftk by:
      1) Removing XFA (so only the AcroForm remains),
      2) Generating an FDF file from 'field_data',
      3) Calling 'pdftk ... fill_form ... flatten' to produce a final PDF.

    Returns the filled PDF as in-memory bytes.

    Raises subprocess.CalledProcessError if pdftk fails
    (e.g., PDF is invalid or pdftk not installed).

    Usage:
        fields = {
            "topmostSubform[0].Page1[0].f1_03[0]": "Hello",
            ...
        }
        pdf_bytes = fill_pdf_with_pdftk("Form_8949_Fillable_2024.pdf", fields)
        # => PDF with fields filled and flattened
    """
    # Get the resolved pdftk path (handles PyInstaller bundles)
    pdftk_bin = get_pdftk_path()

    with tempfile.TemporaryDirectory() as tmpdir:
        # 1) Force removing XFA to ensure an AcroForm
        no_xfa_path = os.path.join(tmpdir, "no_xfa.pdf")
        cmd_drop = [
            pdftk_bin,
            template_path,
            "output",
            no_xfa_path,
            "drop_xfa"
        ]
        subprocess.run(cmd_drop, check=True)
        logger.debug("Dropped XFA from %s => %s", template_path, no_xfa_path)

        # 2) Create the FDF file
        fdf_content = generate_fdf(field_data)
        fdf_path = os.path.join(tmpdir, "data.fdf")
        with open(fdf_path, "w", encoding="utf-8") as fdf_file:
            fdf_file.write(fdf_content)
        logger.debug("Generated FDF at %s with %d fields", fdf_path, len(field_data))

        # 3) Fill form & flatten
        filled_path = os.path.join(tmpdir, "filled_form.pdf")
        cmd_fill = [
            pdftk_bin,
            no_xfa_path,
            "fill_form",
            fdf_path,
            "output",
            filled_path,
            "flatten"
        ]
        subprocess.run(cmd_fill, check=True)
        logger.debug("pdftk fill_form+flatten => %s", filled_path)

        # Return the filled PDF from memory
        with open(filled_path, "rb") as f:
            filled_pdf_bytes = f.read()

    return filled_pdf_bytes
