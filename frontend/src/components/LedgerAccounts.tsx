import React, { useCallback, useEffect, useRef, useState } from "react";
import api from "../api";
import { extractErrorMessage } from "../utils/apiError";
import { accountGroups, ledgerIds, type AccountRow, type YourKind } from "../utils/ledgerAccounts";
import { ACCOUNTS_FAILED, type AccountsState } from "../utils/useAccounts";
import AccountGroupList from "./ledgerAccounts/AccountGroupList";
import DeleteAccountDialog from "./ledgerAccounts/DeleteAccountDialog";
import PastYearDialog from "./PastYearDialog";
import { usePastYearWarning } from "./transactionForm/usePastYearWarning";

interface LedgerAccountsProps extends AccountsState {
  /** Ask the server for the book again, after a change made here or a delete refused; settles once it's there. */
  reload: () => Promise<void>;
  /** A change here moved figures: the 1099-DA switch moves Form 8949 boxes, which Ledger Review reads. */
  onFiguresChanged?: () => void;
}

/**
 * Settings' "Wallets, exchanges and banks" (2.0 spec 5.9; P7's mockups,
 * #572): your accounts grouped by kind, each a row whose details open below
 * it; Add, Rename (#356), Hide or Show, Delete while unused (asked in a
 * dialog, #651), and each
 * exchange's 1099-DA switch, through the past-year warning (5.8). Each
 * change is one request, then the book and the balances again; the server's
 * refusal is shown in its words.
 */
const LedgerAccounts: React.FC<LedgerAccountsProps> = ({ book, failed, reload, onFiguresChanged }) => {
  const [balances, setBalances] = useState<AccountBalance[]>();
  const [busy, setBusy] = useState(false);
  const [refusal, setRefusal] = useState("");
  const [openRow, setOpenRow] = useState<string | null>(null);
  // The row a change was made from: the keyboard goes back to it once the list is new
  const [refocus, setRefocus] = useState<AccountRow | null>(null);
  // The 1099-DA switch moves past years' Form 8949 boxes: asked first (5.8)
  const pastYears = usePastYearWarning();
  const asked = useRef(0);

  // Two changes in a row: only the last answer counts
  const loadBalances = useCallback(() => {
    const ask = ++asked.current;
    return api
      .get<AccountBalance[]>("/calculations/accounts/balances")
      .then((res) => ask === asked.current && setBalances(res.data))
      .catch(() => ask === asked.current && setBalances(undefined)); // the rows show no balance
  }, []);

  useEffect(() => {
    void loadBalances();
  }, [loadBalances]);

  // Hidden, the row is in its group's folded list; shown again, back in the
  // list; deleted, gone: its button if it's there, else "Show hidden", else Add
  useEffect(() => {
    if (!refocus || busy) return;
    const ids = [ledgerIds.rowToggle(refocus.key), ledgerIds.showHidden(refocus.kind), ledgerIds.addButton(refocus.kind)];
    ids.map((id) => document.getElementById(id)).find((el) => el !== null)?.focus();
    setRefocus(null);
  }, [refocus, busy]);

  /** One change, then the book and the balances as they are after it; true when the server made it. */
  const change = async (row: AccountRow | null, request: () => Promise<unknown>): Promise<boolean> => {
    setBusy(true);
    setRefusal("");
    try {
      await request();
      await Promise.all([reload(), loadBalances()]);
      if (row) {
        setOpenRow(null);
        setRefocus(row);
      }
      return true;
    } catch (error) {
      setRefusal(extractErrorMessage(error));
      return false;
    } finally {
      setBusy(false);
    }
  };

  const hide = (row: AccountRow, hidden: boolean) => {
    void change(row, () => api.put(`/accounts/${row.id}`, { hidden }));
  };

  // Delete asks first, in a dialog (#651); it stays open, saying so, while the request runs
  const [deleting, setDeleting] = useState<AccountRow | null>(null);
  // Cancelled, the keyboard goes back to the row's Delete, found by its id: in Safari a click focuses no button
  const cancelDelete = useCallback(() => {
    if (deleting) document.getElementById(ledgerIds.rowDelete(deleting.key))?.focus();
    setDeleting(null);
  }, [deleting]);

  // Refused, the book may be out of date (the account used since it was read, by the AI connector or another tab,
  // #720, or deleted there): it and the balances are read again, so the row says what the server has and offers
  // Delete only if it still may; the keyboard goes back to the row, its Delete button perhaps gone
  const remove = async (row: AccountRow) => {
    const deleted = await change(row, () => api.delete(`/accounts/${row.id}`));
    setDeleting(null);
    if (deleted) return;
    await Promise.all([reload(), loadBalances()]);
    setRefocus(row);
  };

  // A new exchange has no sales, so its 1099-DA answer moves no figure: one request, no past-year warning
  const add = (kind: YourKind, name: string, sends1099da?: boolean) => change(null, () =>
    api.post("/accounts/", sends1099da === undefined ? { kind, name } : { kind, name, sends_1099da: sends1099da }));

  // A name moves no figure, so the server never asks (B6c's save): one request
  const rename = (row: AccountRow, name: string) => {
    void change(row, () => api.put(`/accounts/${row.id}`, { name }));
  };

  // A row opened or closed: a refusal one of its changes got is no longer news, as Add's isn't once it closes
  const toggleRow = (row: AccountRow) => {
    setOpenRow(openRow === row.key ? null : row.key);
    setRefusal("");
  };

  // Either of an exchange's accounts turns the exchange's switch; cancelled, nothing is saved and the box
  // shows the saved setting. The box is never disabled meanwhile: the dialog gives the keyboard back to it as
  // it closes, which a disabled box can't take; a second click is let go instead, and the other changes wait.
  const switchingNow = useRef(false);
  const [switching, setSwitching] = useState(false);
  const switch1099da = async (row: AccountRow, on: boolean) => {
    if (switchingNow.current) return;
    switchingNow.current = true;
    setSwitching(true);
    setRefusal("");
    try {
      const saved = await pastYears.attempt("setting", (confirm) =>
        api.put(`/accounts/${row.id}`, { sends_1099da: on }, confirm ? { params: { confirm } } : undefined));
      if (saved !== null) onFiguresChanged?.();
    } catch (error) {
      setRefusal(extractErrorMessage(error));
    } finally {
      // What's saved, whatever the answer: a confirmed save whose answer was lost shows too
      await reload();
      switchingNow.current = false;
      setSwitching(false);
    }
  };

  if (failed) return <p className="note note-error" role="alert">{ACCOUNTS_FAILED}</p>;
  if (!book) return <p className="loading-row">Loading your accounts…</p>;
  return (
    <div className="ledger-accounts">
      {accountGroups(book).map((group) => (
        <AccountGroupList key={group.kind} group={group} book={book} balances={balances} busy={busy} switching={switching}
          openRow={openRow} onToggleRow={toggleRow}
          onHide={hide} onDelete={setDeleting} onSwitch1099da={(row, on) => void switch1099da(row, on)} onRename={rename}
          onAdd={add}
          onAddClosed={() => setRefusal("")} />
      ))}
      {refusal && <p className="note note-error" role="alert">{refusal}</p>}
      {pastYears.question && <PastYearDialog {...pastYears.question} />}
      {deleting && (
        <DeleteAccountDialog row={deleting} busy={busy} onConfirm={() => void remove(deleting)} onCancel={cancelDelete} />
      )}
      <p className="settings-note">
        An account with transactions can be hidden, never deleted: its history stays on your tax forms.
      </p>
    </div>
  );
};

export default LedgerAccounts;
