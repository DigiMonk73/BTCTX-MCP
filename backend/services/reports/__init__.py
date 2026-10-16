"""
The reports: Form 8949 and Schedule D filled with pypdf, the complete tax
report and the transaction history.

pypdf warns, once per font of each IRS form it reads text from (to check a
draft's year and pages, draft_forms.py) and with the font's whole width
table, about 2 KB a line, that fontTools isn't installed: it would read the
fonts' encodings fully. The forms don't need it (every IRS PDF is read back
field by field in the release tests), and the lines buried real errors in
the service log (#124). Only that message is dropped, here, so it is
wherever the package is used (the CLI's draft install too): every other
pypdf warning still shows.
"""

import logging


class _WithoutFontToolsNotice(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return not str(record.msg).startswith("fontTools is required")


logging.getLogger("pypdf._cmap").addFilter(_WithoutFontToolsNotice())
