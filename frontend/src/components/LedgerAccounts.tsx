import React, { useEffect, useState } from "react";
import api from "../api";
import { balanceText, settingsAccounts } from "../utils/ledgerAccounts";
import { ACCOUNTS_FAILED, useAccounts } from "../utils/useAccounts";
import AccountRow from "./ledgerAccounts/AccountRow";

/** Settings' "Wallets, exchanges and banks" (spec 5.9): your accounts. */
const LedgerAccounts: React.FC<SettingsSectionProps> = () => {
  const { book, failed } = useAccounts();
  const [balances, setBalances] = useState<AccountBalance[]>([]);

  useEffect(() => {
    api
      .get<AccountBalance[]>("/calculations/accounts/balances")
      .then((res) => setBalances(res.data))
      .catch(() => setBalances([]));
  }, []);

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
            />
          ))}
        </ul>
      )}
    </div>
  );
};

export default LedgerAccounts;
