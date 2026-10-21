import React from "react";
import { KIND_LABEL } from "../../utils/ledgerAccounts";

interface AccountRowProps {
  account: LedgerAccount;
  balance: string;
}

const AccountRow: React.FC<AccountRowProps> = ({ account, balance }) => (
  <li className="settings-option" aria-label={account.name}>
    <div className="option-info">
      <span className="settings-option-title">{account.name}</span>
      <span className="settings-option-subtitle">
        {balance ? `${KIND_LABEL[account.kind]} · ${balance}` : KIND_LABEL[account.kind]}
      </span>
      {account.hidden && <span className="badge">Hidden</span>}
    </div>
  </li>
);

export default AccountRow;
