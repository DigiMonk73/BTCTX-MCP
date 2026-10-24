"""
The importer for any exchange's CSV (B5b, #567; the owner's decision 17 on
#251): the mappings, ready-made and the owner's own; a file's columns, for
the screen that matches them; the preview of a file read by a mapping into
the exchange and wallet the owner chose, its rows already in the ledger
marked (#253); and the import, River's own, with its checks by name, its
guard against a second click and its one write lock.

A logged-in session only: the AI key never imports a file nor changes a
mapping (AGENTS.md, "Security rules"). Every route is a plain `def`, run in
a worker thread, so a file's work never holds up the server.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from pydantic import ValidationError
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.routers.csv_import import _read_validated_csv, _require_auth
from backend.routers.river_import import execute_river_import, previewed
from backend.schemas.csv_import import CSVParseError
from backend.schemas.exchange_import import FileColumnsResponse, MappingOut, MappingsResponse, OwnMapping
from backend.schemas.river_import import RiverImportResponse, RiverPreviewResponse
from backend.schemas.user import NOT_TEXT, is_text
from backend.services.account import account_book
from backend.services.exchange_import import file_columns, propose_file
from backend.services.exchange_mappings import (
    READY_MADE,
    Mapping,
    delete_mapping,
    from_own,
    mapping_by_id,
    save_mapping,
    saved_mappings,
)
from backend.services.river_import import river_accounts

router = APIRouter()

CHOOSE_MAPPING = "Choose the exchange whose file this is, or match its columns."
UNSAVED = "unsaved"


@router.get("/mappings", response_model=MappingsResponse)
def list_mappings(request: Request, db: Session = Depends(get_db)):
    """The ready-made mappings, River first, then the owner's own in the order saved."""
    _require_auth(request)
    ready = [MappingOut(id=m.id, name=m.name, ready_made=True, help=m.help, checked=m.checked)
             for m in READY_MADE.values()]
    own = [MappingOut(id=i, name=m.name, ready_made=False, mapping=m) for i, m in saved_mappings(db).items()]
    return MappingsResponse(mappings=[*ready, *own])


@router.post("/mappings", response_model=MappingOut)
def create_mapping(request: Request, mapping: OwnMapping, db: Session = Depends(get_db)):
    """Save a mapping of the owner's; 409 when one of theirs has its name, or they have the most kept."""
    _require_auth(request)
    return MappingOut(id=save_mapping(db, mapping), name=mapping.name, ready_made=False, mapping=mapping)


@router.put("/mappings/{mapping_id}", response_model=MappingOut)
def replace_mapping(request: Request, mapping_id: str, mapping: OwnMapping, db: Session = Depends(get_db)):
    """Replace a mapping of the owner's; 404 when they have none by that id."""
    _require_auth(request)
    return MappingOut(id=save_mapping(db, mapping, mapping_id), name=mapping.name, ready_made=False, mapping=mapping)


@router.delete("/mappings/{mapping_id}", status_code=204)
def remove_mapping(request: Request, mapping_id: str, db: Session = Depends(get_db)):
    """Delete a mapping of the owner's; 404 when they have none by that id."""
    _require_auth(request)
    delete_mapping(db, mapping_id)
    return Response(status_code=204)


@router.post("/columns", response_model=FileColumnsResponse)
def read_columns(request: Request, file: UploadFile = File(...)):
    """
    A file's header and columns, its first rows and the words in each
    column, for matching them to a mapping; and the ready-made mapping
    whose columns it has, if one does. Nothing is written.
    """
    _require_auth(request)
    found = file_columns(_read_validated_csv(file))
    if isinstance(found, CSVParseError):
        raise HTTPException(status_code=400, detail=found.message)
    return FileColumnsResponse(**vars(found))


@router.post("/preview", response_model=RiverPreviewResponse)
def preview_exchange_file(
    request: Request,
    file: UploadFile = File(...),
    mapping_id: str | None = Form(None),
    mapping: str | None = Form(None),
    exchange_account_id: int | None = Form(None),
    wallet_account_id: int | None = Form(None),
    db: Session = Depends(get_db),
):
    """
    Read an exchange's file by a mapping (`mapping_id`, ready-made or the
    owner's, or an unsaved `mapping` as JSON) into the exchange and the
    wallet the owner chose (an exchange's BTC account and a wallet; by
    default the first of each not hidden, 5.11), value its payouts, and mark
    the rows already in the ledger. Nothing is written to the database.
    """
    _require_auth(request)
    content = _read_validated_csv(file)
    chosen = _mapping(db, mapping_id, mapping)
    accounts = river_accounts(account_book(db), exchange_account_id, wallet_account_id)
    return previewed(propose_file(content, chosen, accounts), db)


# The rows a preview showed, as the owner edited them, are River's rows: the
# same checks, duplicate guard and write lock save them (routers/river_import.py)
router.post("/execute", response_model=RiverImportResponse)(execute_river_import)


def _mapping(db: Session, mapping_id: str | None, given: str | None) -> Mapping:
    """The mapping the preview reads by: one saved or ready-made by its id,
    or the owner's unsaved one; exactly one of the two."""
    if (mapping_id is None) == (given is None):
        raise HTTPException(status_code=422, detail=CHOOSE_MAPPING)
    if mapping_id is not None:
        return mapping_by_id(db, mapping_id)
    return from_own(UNSAVED, _own_mapping(given))


def _own_mapping(given: str) -> OwnMapping:
    """An unsaved mapping, from its JSON: refused (422) when it isn't text
    (a lone surrogate can't be said back, #313) or isn't a mapping, its
    problems said without the values sent."""
    try:
        value = json.loads(given)
    except ValueError:
        raise HTTPException(status_code=422, detail="The mapping isn't JSON.") from None
    if not _all_text(value):
        raise HTTPException(status_code=422, detail=NOT_TEXT.format("mapping"))
    try:
        return OwnMapping.model_validate(value)
    except ValidationError as exc:
        said = "; ".join(f"{'.'.join(map(str, e['loc'])) or 'mapping'}: {e['msg']}" for e in exc.errors())
        raise HTTPException(status_code=422, detail=f"The mapping can't be used: {said}") from None


def _all_text(value) -> bool:
    """Whether every string in the JSON value, and every key, is text."""
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, str) and not is_text(item):
            return False
        if isinstance(item, dict):
            pending.extend(item.keys())
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)
    return True
