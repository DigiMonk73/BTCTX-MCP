"""The past-year warning's one answer (spec 5.8).

Every write it covers answers 409 with the same body: the sentence, the
years, what changes, what's pending, and the fingerprint that confirms it.
"""

import hashlib
import json


class PastYearsChange(Exception):  # .body: the 409's JSON; str() is body["detail"]
    def __init__(self, body: dict):
        super().__init__(body["detail"])
        self.body = body


# "tax year 2025" / "tax years 2024 and 2025" / "tax years 2023, 2024 and 2025"
def years_text(years: list[int]) -> str:
    if len(years) == 1:
        return f"tax year {years[0]}"
    named = ", ".join(str(year) for year in years[:-1])
    return f"tax years {named} and {years[-1]}"


def warning_detail(years: list[int], adds: bool = False) -> str:
    head = "This adds to" if adds else "This changes the figures of"
    return (f"{head} {years_text(years)}, which you may already have filed. "
            "Confirm to save it: a copy of your ledger is made first.")


# sha256 of json.dumps(parts, sort_keys=True, default=str)
def fingerprint(*parts) -> str:
    payload = json.dumps(parts, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def warning(years: list[int], changes: list[dict], pending: list[dict], write,
            adds: bool = False, recalc_error: str | None = None) -> PastYearsChange:
    body = {
        "detail": warning_detail(years, adds),
        "years": years,
        "changes": changes,
        "pending": pending,
        "recalc_error": recalc_error,
        "confirm": fingerprint(write, years, changes, pending, recalc_error),
    }
    return PastYearsChange(body)
