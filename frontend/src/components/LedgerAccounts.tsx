import React, { useEffect, useState } from "react";
import api from "../api";
import { extractErrorMessage } from "../utils/apiError";
import { balanceText, pastYearsConfirm, settingsAccounts, type YourKind } from "../utils/ledgerAccounts";
import { ACCOUNTS_FAILED, useAccounts } from "../utils/useAccounts";
import AccountRow from "./ledgerAccounts/AccountRow";
import AddAccount from "./ledgerAccounts/AddAccount";

const ADDED: YourKind[] = ["wallet", "exchange", "bank"];

const NOT_CHANGED = "Not changed.";

/** A PUT through the past-year warning (5.8; B6c's stub): a 409 asking to confirm
 * shows the server's sentence, and Yes sends the same change with ?confirm=. */
async function putConfirmed(url: string, body: object): Promise<void> {
  try {
    await api.put(url, body);
  } catch (error) {
    const confirm = pastYearsConfirm(error);
    if (confirm === null) throw error;
    if (!window.confirm(extractErrorMessage(error))) throw new Error(NOT_CHANGED, { cause: error });
    await api.put(url, body, { params: { confirm } });
  }
}

/** Settings' "Wallets, exchanges and banks" (spec 5.9): your accounts. Every change is one request, then the book again. */
const LedgerAccounts: React.FC<SettingsSectionProps> = ({ loading, setLoading, setMessage }) => {
  const { book, failed, reload } = useAccounts();
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

  const switch1099da = (account: LedgerAccount, sends: boolean) =>
    write(() => putConfirmed(`/accounts/${account.id}`, { sends_1099da: sends }), "Saved.");

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
    </div>
  );
};

export default LedgerAccounts;
