// The question before a save or delete changes an earlier tax year (2.0
// spec 5.8, #352): the server's words, what moves, and the owner's choice.
// Nothing is saved until "Save anyway" (or "Delete anyway"), and the server
// makes a copy of the ledger first.
import React, { useEffect, useLayoutEffect, useRef, useState } from "react";
import { keepFocusIn } from "../utils/dialogFocus";
import {
  byTaxYears, yearsInWords, type PastYearChange, type PastYearKind, type PastYearWarning, type WarnedAgain,
} from "../utils/pastYears";
import { reviewAmount, typeWithSourceOrPurpose } from "../utils/transactionList";

interface PastYearDialogProps {
  kind: PastYearKind;
  warning: PastYearWarning;
  /** The ledger changed after the owner confirmed ("confirmed"), or after
   * the page confirmed an add to a year kept quiet ("quiet"): the server
   * refused, and `warning` is what the save changes now. */
  changed?: WarnedAgain | null;
  /** The confirmed request is running */
  busy: boolean;
  /** What opened it, focused again when it closes. */
  opener: React.RefObject<HTMLElement | null>;
  /** `quiet`: the owner ticked "Don't ask again" (adds only). */
  onConfirm: (quiet: boolean) => void;
  onCancel: () => void;
}

const PENDING_TITLE = "These also change, from rules fixed since they were saved";

/** Changes as Ledger Review lists them, under their tax years when they're in more than one. */
const ChangeList: React.FC<{ items: PastYearChange[] }> = ({ items }) => {
  const groups = byTaxYears(items);
  return (
    <>
      {groups.map((group) => (
        <div key={group.label} className="dialog-section">
          {groups.length > 1 && <strong className="dialog-note">{group.label}</strong>}
          <ul className="dialog-list" aria-label={group.label || undefined}>
            {group.items.map((item, i) => (
              <li key={`${item.id ?? "new"}-${i}`}>
                {item.date} · {typeWithSourceOrPurpose(item)} · {reviewAmount(item)} — {item.change}
              </li>
            ))}
          </ul>
        </div>
      ))}
    </>
  );
};

/** What the save also applies, and why Recalculate Ledger can't run, apart from the save's own changes. */
const PendingChanges: React.FC<{ warning: PastYearWarning }> = ({ warning }) => (
  <div className="dialog-section" role="group" aria-labelledby="past-year-pending">
    <div id="past-year-pending" className="dialog-note">{PENDING_TITLE}</div>
    <ChangeList items={warning.pending} />
    {warning.recalc_error && (
      <div className="note note-warning">Recalculate Ledger can't run now: {warning.recalc_error}</div>
    )}
  </div>
);

/**
 * The zone the rows' dates are in, under them: the server's, the tax
 * timezone (the one being saved, for a timezone), as Ledger Review's are,
 * not the device's clock the form behind it shows (#737).
 */
const DatesNote: React.FC<{ warning: PastYearWarning }> = ({ warning }) =>
  warning.timezone && warning.changes.length + warning.pending.length > 0
    ? <p className="dialog-note">Dates in {warning.timezone}.</p>
    : null;

const PastYearDialog: React.FC<PastYearDialogProps> = ({
  kind, warning, changed = null, busy, opener, onConfirm, onCancel,
}) => {
  const [quiet, setQuiet] = useState(false);
  const dialog = useRef<HTMLDivElement>(null);
  const cancelButton = useRef<HTMLButtonElement>(null);
  // Cancel first, so Enter or Space straight away saves nothing; and a new
  // warning is answered anew, for the years it names now
  useLayoutEffect(() => {
    setQuiet(false);
    cancelButton.current?.focus();
  }, [warning.confirm]);
  // While its request runs nothing in it can take focus: it holds it itself,
  // so Tab never reaches the form behind it
  useEffect(() => {
    if (busy) dialog.current?.focus();
  }, [busy]);
  // Focus goes back to what opened the dialog when it closes
  useEffect(() => {
    const from = opener.current;
    return () => from?.focus();
  }, [opener]);
  // On the document, before the panel's own Escape (which closes the panel
  // unless the key was taken): Escape here is the dialog's, busy or not
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        if (!busy) onCancel();
      }
      keepFocusIn(dialog.current, e);
    };
    document.addEventListener("keydown", onKey, true);
    return () => document.removeEventListener("keydown", onKey, true);
  }, [busy, onCancel]);

  const years = yearsInWords(warning.years);
  const hasPending = warning.pending.length > 0 || warning.recalc_error !== null;
  return (
    <div className="dialog-backdrop">
      <div ref={dialog} tabIndex={-1} className="dialog card" role="dialog" aria-modal="true"
        aria-labelledby="past-year-title" aria-describedby="past-year-detail">
        <h3 id="past-year-title" className="card-title">Change an earlier tax year?</h3>
        <p id="past-year-detail">{warning.detail}</p>
        {changed && (
          // Keyed by the warning, so a second change is announced again
          <div key={warning.confirm} className="note note-error" role="alert">
            {changed === "quiet" ? "The ledger changed as this page confirmed it for you."
              : "The ledger changed while this was open."} Nothing was {kind === "delete" ? "deleted" : "saved"}:
            check what this changes now.
          </div>
        )}
        {!warning.exact && warning.why_not_exact && <p className="dialog-note">{warning.why_not_exact}</p>}
        <ChangeList items={warning.changes} />
        {hasPending && <PendingChanges warning={warning} />}
        <DatesNote warning={warning} />
        {kind === "add" && years && (
          <label className="dialog-tick">
            <input type="checkbox" checked={quiet} disabled={busy} onChange={(e) => setQuiet(e.target.checked)} />
            <span>Don't ask again for adds to {years} while this page is open</span>
          </label>
        )}
        {busy && (
          <div className="loading-row" role="status">
            <div className="spinner"></div>
            <span>{kind === "delete" ? "Making a copy, then deleting…" : "Making a copy, then saving…"}</span>
          </div>
        )}
        <div className="dialog-actions">
          <button ref={cancelButton} type="button" className="btn btn-secondary" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
          <button type="button" className={kind === "delete" ? "btn btn-danger" : "btn btn-primary"}
            onClick={() => onConfirm(kind === "add" && quiet)} disabled={busy}>
            {kind === "delete" ? "Delete anyway (a copy is made first)" : "Save anyway (a copy is made first)"}
          </button>
        </div>
      </div>
    </div>
  );
};

export default PastYearDialog;
