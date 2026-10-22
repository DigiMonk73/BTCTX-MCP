// The past-year warning's dialog (spec 5.8): a save, an edit, a delete or an
// exchange's 1099-DA switch that changes the figures of an earlier tax year
// says which years and what changes before anything is saved. Save anyway
// sends it again confirmed; the server makes a copy of the ledger first.
import React, { useEffect, useRef, useState } from "react";
import { keepFocusIn } from "../utils/dialogFocus";
import { itemText, yearsText, type PastYearsItem, type PastYearsWarning } from "../utils/pastYears";

const ItemList: React.FC<{ label: string; items: PastYearsItem[] }> = ({ label, items }) => {
  if (items.length === 0) return null;
  return (
    <ul className="dialog-list" aria-label={label}>
      {items.map((item) => (
        <li key={item.id}>{itemText(item)}</li>
      ))}
    </ul>
  );
};

const PastYearsDialog: React.FC<{
  warning: PastYearsWarning;
  forAdd: boolean;
  onSave: (stopAsking: boolean) => void;
  onCancel: () => void;
}> = ({ warning, forAdd, onSave, onCancel }) => {
  const [stopAsking, setStopAsking] = useState(false);
  const dialog = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onCancel();
      }
      keepFocusIn(dialog.current, e);
    };
    // In the capture phase, marked handled: the transaction panel's own Escape
    // (close the panel) skips a key the dialog took
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [onCancel]);

  return (
    <div className="dialog-backdrop">
      <div ref={dialog} className="dialog card" role="dialog" aria-modal="true"
        aria-labelledby="past-years-title" aria-describedby="past-years-detail">
        <h3 id="past-years-title" className="card-title">Change an earlier tax year?</h3>
        <p id="past-years-detail">{warning.detail}</p>
        {warning.changes.length > 0 && <ItemList label="What changes" items={warning.changes} />}
        {warning.pending.length > 0 && (
          <div className="dialog-section">
            <p className="dialog-note">These also change, from rules fixed since they were saved:</p>
            <ItemList label="These also change" items={warning.pending} />
          </div>
        )}
        {warning.recalc_error && (
          <p className="dialog-note">Recalculate Ledger can't run now: {warning.recalc_error}</p>
        )}
        {forAdd && (
          <label className="dialog-check">
            <input type="checkbox" checked={stopAsking}
              onChange={(e) => setStopAsking(e.target.checked)} />
            Don't ask again for adds to {yearsText(warning.years)} while this page is open
          </label>
        )}
        <div className="dialog-actions">
          {/* Cancel first and focused: Enter never saves into a filed year by itself */}
          <button type="button" className="btn btn-secondary" onClick={onCancel} autoFocus>Cancel</button>
          <button type="button" className="btn btn-primary"
            onClick={() => onSave(stopAsking)}>Save anyway (a copy is made first)</button>
        </div>
      </div>
    </div>
  );
};

export default PastYearsDialog;
