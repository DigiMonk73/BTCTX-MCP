import React from "react";
import { KIND_LABEL } from "../../utils/ledgerAccounts";

interface AccountRowProps {
  account: LedgerAccount;
  balance: string;
  busy: boolean;
  onHide: (account: LedgerAccount, hidden: boolean) => void;
  onDelete: (account: LedgerAccount) => void;
}

/** One of your accounts in Settings: nickname, kind and balance, "Hidden" when it is; Hide or Show, and Delete while no transaction names it (5.9). */
const AccountRow: React.FC<AccountRowProps> = ({ account, balance, busy, onHide, onDelete }) => (
  <li className="settings-option" aria-label={account.name}>
    <div className="option-info">
      <span className="settings-option-title">{account.name}</span>
      <span className="settings-option-subtitle">
        {balance ? `${KIND_LABEL[account.kind]} · ${balance}` : KIND_LABEL[account.kind]}
      </span>
      {account.hidden && <span className="badge">Hidden</span>}
    </div>
    <div className="ledger-account-actions">
      <button type="button" className="btn btn-secondary btn-sm" disabled={busy} onClick={() => onHide(account, !account.hidden)}>
        {account.hidden ? "Show" : "Hide"}
      </button>
      {!account.in_use && (
        <button type="button" className="btn btn-secondary btn-sm" disabled={busy} onClick={() => onDelete(account)}>Delete</button>
      )}
    </div>
  </li>
);

export default AccountRow;
