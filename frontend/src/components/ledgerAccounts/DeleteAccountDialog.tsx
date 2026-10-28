// The question before an unused account is deleted (#651), in BitcoinTX's
// own dialog as Delete All's is, never the browser's confirm box: what goes
// (an exchange: both its accounts) and the rule the server keeps.
import React, { useCallback, useEffect, useRef } from "react";
import { keepFocusIn } from "../../utils/dialogFocus";
import type { AccountRow } from "../../utils/ledgerAccounts";

interface DeleteAccountDialogProps {
  row: AccountRow;
  /** The delete is running */
  busy: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/** "the wallet Coldcard", or "the exchange Kraken and both its accounts, Kraken USD and Kraken BTC". */
function whatGoes(row: AccountRow): string {
  if (row.kind !== "exchange") return `the ${row.kind} ${row.name}`;
  const [usd, btc] = row.accounts.map((account) => account.name);
  return `the exchange ${row.name} and both its accounts, ${usd} and ${btc}`;
}

const DeleteAccountDialog: React.FC<DeleteAccountDialogProps> = ({ row, busy, onConfirm, onCancel }) => {
  const dialog = useRef<HTMLDivElement>(null);
  const cancelButton = useRef<HTMLButtonElement>(null);
  // Cancel first, so Enter or Space straight away deletes nothing; cancelled, the keyboard goes back to
  // what opened it (Delete). Deleted or refused, the section puts it on the row instead.
  const cancelled = useRef(false);
  useEffect(() => {
    const from = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    cancelButton.current?.focus();
    return () => {
      if (cancelled.current) from?.focus();
    };
  }, []);
  // While its request runs nothing in it can take focus: it holds it itself
  useEffect(() => {
    if (busy) dialog.current?.focus();
  }, [busy]);
  const cancel = useCallback(() => {
    cancelled.current = true;
    onCancel();
  }, [onCancel]);
  // On the document, before Settings' own keys: Escape here is the dialog's, busy or not
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        if (!busy) cancel();
      }
      keepFocusIn(dialog.current, e);
    };
    document.addEventListener("keydown", onKey, true);
    return () => document.removeEventListener("keydown", onKey, true);
  }, [busy, cancel]);

  const many = row.kind === "exchange";
  return (
    <div className="dialog-backdrop">
      <div ref={dialog} tabIndex={-1} className="dialog dialog-narrow card" role="dialog" aria-modal="true"
        aria-labelledby="delete-account-title" aria-describedby="delete-account-what">
        <h3 id="delete-account-title" className="card-title">Delete {row.name}?</h3>
        <p id="delete-account-what">
          This deletes {whatGoes(row)}. Only an account with no transactions can be deleted, and{" "}
          {many ? "they have" : "it has"} none.
        </p>
        <p className="dialog-note">An account with transactions can be hidden instead: its history stays.</p>
        <div className="dialog-actions">
          <button ref={cancelButton} type="button" className="btn btn-secondary" onClick={cancel} disabled={busy}>
            Cancel
          </button>
          <button type="button" className="btn btn-danger" onClick={onConfirm} disabled={busy}>
            {busy ? "Deleting..." : `Delete ${row.name}`}
          </button>
        </div>
      </div>
    </div>
  );
};

export default DeleteAccountDialog;
