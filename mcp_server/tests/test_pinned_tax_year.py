"""
The connector's tests drive the backend in-process, in the same pytest run as
the backend's: "this tax year" (services/tax_time.current_tax_year, 2.0 plan
5.15) is pinned for them too, whichever tests ran before on the worker, so no
write they make meets the past-year warning (5.8).
"""

from zoneinfo import ZoneInfo

from backend.services import tax_time
from backend.tests.conftest import PINNED_TAX_YEAR


def test_this_tax_year_is_the_backend_tests():
    assert tax_time.current_tax_year(ZoneInfo("Asia/Tokyo")) == PINNED_TAX_YEAR == 2009
