"""
The importer for any exchange's file (B5b): the owner's own mapping, the
mappings listed, and a file's columns for the screen that matches them.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.services.tax_time import validate_timezone

# What a file's word for a row can mean (exchange_mappings.KINDS)
Kind = Literal["buy", "sell", "send", "receive", "income", "interest", "reward", "rebate",
               "dollars", "convert", "leave out"]
# A column's name as a header gives it; a word or a status as a cell does
Name = Field(min_length=1, max_length=200)


class OwnColumns(BaseModel):
    """Which of the file's columns hold what, each by its header's name."""
    model_config = ConfigDict(extra="forbid")

    date: str = Name
    kind: str = Name
    btc: str = Name
    time: str | None = Field(None, min_length=1, max_length=200)
    usd: str | None = Field(None, min_length=1, max_length=200)
    fee: str | None = Field(None, min_length=1, max_length=200)
    fee_currency: str | None = Field(None, min_length=1, max_length=200)
    fee_btc: str | None = Field(None, min_length=1, max_length=200)
    asset: str | None = Field(None, min_length=1, max_length=200)
    status: str | None = Field(None, min_length=1, max_length=200)
    row_id: str | None = Field(None, min_length=1, max_length=200)


class OwnMapping(BaseModel):
    """
    A mapping the owner makes for an exchange's file: its columns, what each
    of the file's words for a row means, the zone of its times ("UTC", a
    zone such as America/Chicago, or "dates" when every date carries its
    own), which kinds' dollars include the fee (a buy's total paid, a sell's
    net received), whether a send's bitcoin includes its network fee, how
    its numbers and dates are written, the asset column's words for bitcoin
    and the status column's words for a completed row.
    """
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=60)
    columns: OwnColumns
    kinds: dict[str, Kind] = Field(min_length=1, max_length=200)
    zone: str = "UTC"
    dollars_after_fee: list[Literal["buy", "sell"]] = Field(default_factory=list, max_length=2)
    send_fee_included: bool = False
    decimal_comma: bool = False
    day_first: bool = False
    btc_assets: list[str] = Field(default_factory=lambda: ["BTC"], min_length=1, max_length=20)
    done: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("name")
    @classmethod
    def _named(cls, name: str) -> str:
        if not name.strip():
            raise ValueError("A mapping needs a name.")
        return name.strip()

    @field_validator("kinds")
    @classmethod
    def _words(cls, kinds: dict[str, str]) -> dict[str, str]:
        if any(not word.strip() or len(word) > 200 for word in kinds):
            raise ValueError("Each word for a kind of row has 1 to 200 characters.")
        return kinds

    @field_validator("btc_assets", "done")
    @classmethod
    def _cells(cls, words: list[str]) -> list[str]:
        if any(not word.strip() or len(word) > 200 for word in words):
            raise ValueError("Each word has 1 to 200 characters.")
        return words

    @field_validator("zone")
    @classmethod
    def _zone(cls, zone: str) -> str:
        return zone if zone in ("UTC", "dates") else validate_timezone(zone)


class MappingOut(BaseModel):
    """A mapping the screen lists: a ready-made one with where to download
    its file, or the owner's own with what it holds, to edit."""
    id: str
    name: str
    ready_made: bool
    help: str = ""
    mapping: OwnMapping | None = None


class MappingsResponse(BaseModel):
    mappings: list[MappingOut]


class FileColumnsResponse(BaseModel):
    """A file's header (its row in the file) and columns, its first rows,
    and the words found in each column (up to MAX_VALUES), for matching
    them; the ready-made mapping whose columns it has, if one does."""
    header_row: int
    columns: list[str]
    samples: list[list[str]]
    values: dict[str, list[str]]
    looks_like: str | None = None
