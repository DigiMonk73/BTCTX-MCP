"""
Reading the IRS forms leaves pypdf's "fontTools is required" warning out of
the log (#124). pypdf wrote it once per font of each form it read text from
(draft_forms.py checks a draft's year and pages), with the font's whole
width table, about 2 KB a line, burying real errors. Every other pypdf
warning still shows.
"""

import logging

from backend.routers.reports import get_supported_years, get_template_path
from backend.services.reports import draft_forms

NOTICE = "fontTools is required"


def test_reading_the_forms_logs_no_fonttools_notice(caplog):
    year = max(get_supported_years())
    with caplog.at_level(logging.WARNING):
        for form in ("f8949.pdf", "f1040sd.pdf"):
            assert draft_forms.printed_year(get_template_path(year, form)) == year
    assert not [r for r in caplog.records if NOTICE in r.getMessage()]


def test_other_pypdf_warnings_still_show(caplog):
    with caplog.at_level(logging.WARNING):
        logging.getLogger("pypdf._cmap").warning("Advanced encoding /Foo not implemented yet")
        logging.getLogger("pypdf._reader").warning("Ignoring wrong pointing object 6 0 (offset 0)")
    assert [r.getMessage() for r in caplog.records] == [
        "Advanced encoding /Foo not implemented yet", "Ignoring wrong pointing object 6 0 (offset 0)"]
