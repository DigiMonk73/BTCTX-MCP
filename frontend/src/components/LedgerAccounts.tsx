import React, { useCallback, useEffect, useState } from "react";
import api from "../api";
import { extractErrorMessage } from "../utils/apiError";
import { accountGroups, type AccountRow, type YourKind } from "../utils/ledgerAccounts";
import { ACCOUNTS_FAILED, type AccountsState } from "../utils/useAccounts";
import AccountGroupList from "./ledgerAccounts/AccountGroupList";

interface LedgerAccountsProps extends AccountsState {
  /** Ask the server for the book again, after a change made here. */
  reload: () => void;
}

/**
 * Settings' "Wallets, exchanges and banks" (2.0 spec 5.9; P7's mockups,
 * #572): your accounts grouped by kind, each a row whose details open below
 * it; Add, Hide or Show, and Delete while unused. Each change is one request,
 * then the book and the balances again; the server's refusal is shown in its
 * words. Renames come with B8.
 */
const LedgerAccounts: React.FC<LedgerAccountsProps> = ({ book, failed, reload }) => {
  const [balances, setBalances] = useState<AccountBalance[]>();
  const [busy, setBusy] = useState(false);
  const [refusal, setRefusal] = useState("");
  const [openRow, setOpenRow] = useState<string | null>(null);

  const loadBalances = useCallback(() => {
    api
      .get<AccountBalance[]>("/calculations/accounts/balances")
      .then((res) => setBalances(res.data))
      .catch(() => setBalances(undefined)); // the rows show no balance
  }, []);

  useEffect(loadBalances, [loadBalances]);

  /** One change; true when the server made it. */
  const change = async (request: () => Promise<unknown>): Promise<boolean> => {
    setBusy(true);
    setRefusal("");
    try {
      await request();
      reload();
      loadBalances();
      return true;
    } catch (error) {
      setRefusal(extractErrorMessage(error));
      return false;
    } finally {
      setBusy(false);
    }
  };

  // The row moves between its group's lists: it closes, as it would if it were new
  const hide = (row: AccountRow, hidden: boolean) => {
    void change(() => api.put(`/accounts/${row.id}`, { hidden })).then((done) => done && setOpenRow(null));
  };

  const remove = (row: AccountRow) => {
    if (!window.confirm(`Delete ${row.name}? It has no transactions.`)) return;
    void change(() => api.delete(`/accounts/${row.id}`)).then((done) => done && setOpenRow(null));
  };

  const add = (kind: YourKind, name: string) => change(() => api.post("/accounts/", { kind, name }));

  if (failed) return <p className="note note-error" role="alert">{ACCOUNTS_FAILED}</p>;
  if (!book) return <p className="loading-row">Loading your accounts…</p>;
  return (
    <div className="ledger-accounts">
      {accountGroups(book).map((group) => (
        <AccountGroupList key={group.kind} group={group} book={book} balances={balances} busy={busy}
          openRow={openRow} onToggleRow={(row) => setOpenRow(openRow === row.key ? null : row.key)}
          onHide={hide} onDelete={remove} onAdd={add} onAddClosed={() => setRefusal("")} />
      ))}
      {refusal && <p className="note note-error" role="alert">{refusal}</p>}
      <p className="settings-note">
        An account with transactions can be hidden, never deleted: its history stays on your tax forms.
      </p>
    </div>
  );
};

export default LedgerAccounts;
