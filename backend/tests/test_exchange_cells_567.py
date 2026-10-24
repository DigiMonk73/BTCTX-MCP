"""
Reading an exchange's cells (B5b, #567): the numbers and moments exchanges
write. What a cell can't say for sure is refused for its row, never guessed:
a decimal comma read as a thousands one makes "0,5" BTC 5 (#452), and an hour
off moves a payout's price and the minute the duplicate check matches (#253).
"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from backend.services.exchange_cells import RowError, read_moment, read_number, rows_said


@pytest.mark.parametrize("text, decimal_comma, expected", [
    ("1234.56", False, "1234.56"),
    ("$1,234.56", False, "1234.56"),
    ("-$1,252.41", False, "-1252.41"),
    ("$-100.00", False, "-100.00"),
    ("($105.00)", False, "-105.00"),
    ("$1", False, "1"),
    ("0.00000464 BTC", False, "0.00000464"),
    ("USD 5.00", False, "5.00"),
    ("+0.5", False, "0.5"),
    (".5", False, "0.5"),
    ("-0.0020000000", False, "-0.0020000000"),
    ("1.234,56", True, "1234.56"),
    ("0,5", True, "0.5"),
    ("-1.000", True, "-1000"),
])
def test_a_number_as_exchanges_write_it(text, decimal_comma, expected):
    assert read_number(text, decimal_comma) == Decimal(expected)


@pytest.mark.parametrize("text", ["", "  ", "-", "—"])
def test_a_blank_cell_is_no_number(text):
    assert read_number(text) is None


@pytest.mark.parametrize("text, decimal_comma", [
    ("0,5", False), ("1,23", False), ("1.234,56", False), ("1,234.56", True), ("abc", False), ("1e5", False),
    ("€5", False), ("1 000", False), ("--5", False), ("$", False), ("NaN", False), ("Infinity", False),
])
def test_a_number_that_cant_be_read_for_sure_is_refused(text, decimal_comma):
    with pytest.raises(RowError):
        read_number(text, decimal_comma, "Amount")


UTC = timezone.utc


@pytest.mark.parametrize("text, zone, expected", [
    ("2025-01-15 14:23:11", "UTC", datetime(2025, 1, 15, 14, 23, 11, tzinfo=UTC)),
    ("2025-01-15 14:23:11.1234", "UTC", datetime(2025, 1, 15, 14, 23, 11, tzinfo=UTC)),
    ("2025-01-15T14:23:11Z", "America/Chicago", datetime(2025, 1, 15, 14, 23, 11, tzinfo=UTC)),
    ("2025-01-15T14:23:11.5Z", "UTC", datetime(2025, 1, 15, 14, 23, 11, tzinfo=UTC)),
    ("2025-01-15T09:23:11-05:00", "UTC", datetime(2025, 1, 15, 14, 23, 11, tzinfo=UTC)),
    ("2024-11-16 17:39:46+00", "UTC", datetime(2024, 11, 16, 17, 39, 46, tzinfo=UTC)),
    ("2024-11-16 12:39:46-0500", "UTC", datetime(2024, 11, 16, 17, 39, 46, tzinfo=UTC)),
    ("2025-01-15 14:23:11 UTC", "America/Chicago", datetime(2025, 1, 15, 14, 23, 11, tzinfo=UTC)),
    ("2025-12-30 23:22:22 PST", "dates", datetime(2025, 12, 31, 7, 22, 22, tzinfo=UTC)),
    ("2025-07-04 12:00:00 PDT", "dates", datetime(2025, 7, 4, 19, 0, 0, tzinfo=UTC)),
    ("2025-01-10 09:15:00 est", "dates", datetime(2025, 1, 10, 14, 15, 0, tzinfo=UTC)),
    ("Jan 15 2025 06:37:33", "UTC", datetime(2025, 1, 15, 6, 37, 33, tzinfo=UTC)),
    ("Jan 5, 2025 6:37 PM", "UTC", datetime(2025, 1, 5, 18, 37, tzinfo=UTC)),
    ("01/15/2025 14:23", "UTC", datetime(2025, 1, 15, 14, 23, tzinfo=UTC)),
    ("2025-04-01 09:00", "America/Chicago", datetime(2025, 4, 1, 14, 0, tzinfo=UTC)),
    ("2025-01-01 09:00", "America/Chicago", datetime(2025, 1, 1, 15, 0, tzinfo=UTC)),
])
def test_a_moment_as_exchanges_write_it(text, zone, expected):
    assert read_moment(text, zone) == expected


def test_day_first_reads_a_european_date():
    assert read_moment("02/03/2025 10:00", "UTC", day_first=True) == datetime(2025, 3, 2, 10, tzinfo=UTC)
    assert read_moment("02/03/2025 10:00", "UTC") == datetime(2025, 2, 3, 10, tzinfo=UTC)


@pytest.mark.parametrize("text, zone", [
    ("2025-03-09 02:30:00", "America/Chicago"),  # the clocks skip it
    ("2025-11-02 01:30:00", "America/Chicago"),  # the clocks pass it twice
    ("2025-01-15 14:23:11", "dates"),  # the file's dates say their zone, this one doesn't
    ("2025-01-15", "UTC"),  # a date alone: the duplicate check needs the minute
    ("15 Janvier 2025 10:00", "UTC"),
    ("2025-01-15 14:23:11 XYZ", "UTC"),
    ("not a date", "UTC"),
])
def test_a_moment_that_cant_be_read_for_sure_is_refused(text, zone):
    with pytest.raises(RowError):
        read_moment(text, zone)


@pytest.mark.parametrize("numbers, said", [
    ([5], "Row 5"),
    ([5, 9], "Rows 5 and 9"),
    ([5, 9, 12], "Rows 5, 9 and 12"),
    (list(range(1, 26)), "Rows 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, … and 5 more"),
])
def test_rows_as_a_warning_names_them(numbers, said):
    assert rows_said(numbers) == said
