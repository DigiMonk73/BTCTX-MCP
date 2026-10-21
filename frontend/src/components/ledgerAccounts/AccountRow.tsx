import React from "react";
import { KIND_LABEL } from "../../utils/ledgerAccounts";

interface AccountRowProps {
  account: LedgerAccount;
  balance: string;
  busy: boolean;
  onHide: (account: LedgerAccount, hidden: boolean) => void;
  onDelete: (account: LedgerAccount) => void;
  onSwitch1099da: (account: LedgerAccount, sends: boolean) => void;
}

const SWITCH_LABEL = "This exchange sends me a Form 1099-DA";
const SWITCH_HELP =
  "An exchange in the US sends one for your sales from 2025; one outside the US usually doesn't. It decides the Form 8949 box, not the gain.";

/** One of your accounts in Settings: nickname, kind and balance, "Hidden" when it is; Hide or Show, and Delete while no transaction names it (5.9). An exchange's switch is on its bitcoin account's row. */
const AccountRow: React.FC<AccountRowProps> = ({ account, balance, busy, onHide, onDelete, onSwitch1099da }) => (
  <li className="settings-option" aria-label={account.name}>
    <div className="option-info">
      <span className="settings-option-title">{account.name}</span>
      <span className="settings-option-subtitle">
        {balance ? `${KIND_LABEL[account.kind]} · ${balance}` : KIND_LABEL[account.kind]}
      </span>
      {account.hidden && <span className="badge">Hidden</span>}
      {account.kind === "exchange" && account.currency === "BTC" && (
        <>
          <label className="ledger-1099da">
            <input
              type="checkbox"
              checked={account.sends_1099da ?? true}
              disabled={busy}
              onChange={(e) => onSwitch1099da(account, e.target.checked)}
            />
            {SWITCH_LABEL}
          </label>
          <span className="settings-option-subtitle">{SWITCH_HELP}</span>
        </>
      )}
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
