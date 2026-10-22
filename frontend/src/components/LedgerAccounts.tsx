import React, { useEffect, useState } from "react";
import api from "../api";
import { extractErrorMessage } from "../utils/apiError";
import { balanceText, settingsAccounts, type YourKind } from "../utils/ledgerAccounts";
import { confirmed } from "../utils/pastYears";
import { ACCOUNTS_FAILED, useAccounts } from "../utils/useAccounts";
import { usePastYears } from "../utils/usePastYears";
import AccountRow from "./ledgerAccounts/AccountRow";
import AddAccount from "./ledgerAccounts/AddAccount";

const ADDED: YourKind[] = ["wallet", "exchange", "bank"];

const NOT_CHANGED = "Not changed.";

/** Settings' "Wallets, exchanges and banks" (spec 5.9): your accounts, their
 * changes and the three Add buttons. Every change is one request, then the book again. */
const LedgerAccounts: React.FC<SettingsSectionProps> = ({ loading, setLoading, setMessage }) => {
  const { book, failed, reload } = useAccounts();
  // The 1099-DA switch moves boxes: through the past-year warning (5.8; B6c's stub)
  const pastYears = usePastYears();
  const [balances, setBalances] = useState<AccountBalance[]>([]);

  useEffect(() => {
    api
      .get<AccountBalance[]>("/calculations/accounts/balances")
      .then((res) => setBalances(res.data))
      .catch(() => setBalances([]));
  }, []);

  /** One change: the server's refusal is shown as it says it. True when it was made. */
  const write = async (request: () => Promise<unknown>, done: string): Promise<boolean> => {
    setLoading(true);
    setMessage("");
    try {
      await request();
      reload();
      setMessage(done);
      return true;
    } catch (error) {
      setMessage(extractErrorMessage(error));
      return false;
    } finally {
      setLoading(false);
    }
  };

  const hide = (account: LedgerAccount, hidden: boolean) =>
    write(() => api.put(`/accounts/${account.id}`, { hidden }), hidden ? "Hidden." : "Shown.");

  const remove = (account: LedgerAccount) => {
    if (!window.confirm(`Delete ${account.name}?`)) return;
    void write(() => api.delete(`/accounts/${account.id}`), "Deleted.");
  };

  const add = (kind: YourKind, name: string) =>
    write(() => api.post("/accounts/", { kind, name }), "Added.");

  const rename = (account: LedgerAccount, name: string) =>
    write(() => api.put(`/accounts/${account.id}`, { name }), "Renamed.");

  const switch1099da = (account: LedgerAccount, sends: boolean) => {
    const url = `/accounts/${account.id}`;
    const put = (confirm?: string) =>
      api.put(url, { sends_1099da: sends }, confirmed(confirm));
    return write(async () => {
      const saved = await pastYears.through(put, false);
      if (saved === null) throw new Error(NOT_CHANGED);
    }, "Saved.");
  };

  return (
    <div className="settings-section" role="region" aria-label="Wallets, exchanges and banks">
      <h3 className="section-title">Wallets, exchanges and banks</h3>
      {failed && <p className="note" role="alert">{ACCOUNTS_FAILED}</p>}
      {book && (
        <ul className="ledger-accounts" aria-label="Your accounts">
          {settingsAccounts(book).map((account) => (
            <AccountRow
              key={account.id}
              account={account}
              balance={balanceText(balances, account)}
              busy={loading}
              onHide={hide}
              onDelete={remove}
              onSwitch1099da={switch1099da}
              onRename={rename}
            />
          ))}
        </ul>
      )}
      {book && (
        <div className="ledger-add">
          {ADDED.map((kind) => (
            <AddAccount key={kind} kind={kind} book={book} busy={loading} onAdd={add} />
          ))}
        </div>
      )}
      {pastYears.dialog}
    </div>
  );
};

export default LedgerAccounts;
