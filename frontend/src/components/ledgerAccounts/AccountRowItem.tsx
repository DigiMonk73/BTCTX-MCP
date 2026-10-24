import React from "react";
import { ChevronDown } from "lucide-react";
import { KIND_LABEL, canDelete, ledgerIds, sends1099da, type AccountRow } from "../../utils/ledgerAccounts";
import ExchangeSwitch from "./ExchangeSwitch";
import RenameAccount from "./RenameAccount";

interface AccountRowItemProps {
  row: AccountRow;
  balance: string;
  open: boolean;
  busy: boolean;
  /** An exchange's switch is saving: Hide, Show and Delete wait; the switch itself never turns grey. */
  switching: boolean;
  onToggle: (row: AccountRow) => void;
  onHide: (row: AccountRow, hidden: boolean) => void;
  onDelete: (row: AccountRow) => void;
  /** An exchange's 1099-DA switch turned on or off. */
  onSwitch1099da: (row: AccountRow, on: boolean) => void;
  /** A new name sent; true once the server made it (#356). */
  onRename: (row: AccountRow, name: string) => Promise<boolean>;
}

// The API's own words for what it refuses (services/account.py), said before it's asked
const IN_USE = "This account has transactions, so it can't be deleted. Hide it instead: its history stays.";
const FIRST_OF_EACH = "Your first bank, wallet and exchange can't be deleted. Hide one you don't use.";

/** One of your accounts (an exchange: its two) as a row: its name, kind and
 * balance; its details, Rename, an exchange's 1099-DA switch, Hide or Show
 * and Delete while unused, open below it. */
const AccountRowItem: React.FC<AccountRowItemProps> = ({
  row, balance, open, busy, switching, onToggle, onHide, onDelete, onSwitch1099da, onRename,
}) => {
  const details = ledgerIds.rowDetails(row.key);
  const deletable = canDelete(row);
  const sends = sends1099da(row);
  return (
    <li className="ledger-account">
      <button
        type="button"
        id={ledgerIds.rowToggle(row.key)}
        className="ledger-account-toggle"
        aria-expanded={open}
        aria-controls={open ? details : undefined}
        onClick={() => onToggle(row)}
      >
        <span className="ledger-account-text">
          <span className="ledger-account-name">{row.name}</span>{" "}
          <span className="ledger-account-kind">
            {KIND_LABEL[row.kind]}
            {row.hidden && <span className="badge ledger-account-hidden">Hidden</span>}
          </span>
        </span>{" "}
        <span className="ledger-account-balance">{balance}</span>
        <ChevronDown className="ledger-account-chevron" size={18} aria-hidden="true" />
      </button>
      {open && (
        <div id={details} className="ledger-account-details" role="region" aria-label={row.name}>
          <RenameAccount row={row} busy={busy || switching} onRename={onRename} />
          {sends !== null && (
            <ExchangeSwitch rowKey={row.key} on={sends} busy={busy} onChange={(on) => onSwitch1099da(row, on)} />
          )}
          <div className="ledger-account-actions">
            <button type="button" className="btn btn-secondary btn-sm" disabled={busy || switching}
              onClick={() => onHide(row, !row.hidden)}>
              {row.hidden ? "Show" : "Hide"}
            </button>
            {deletable && (
              <button type="button" className="btn btn-danger btn-sm" disabled={busy || switching}
                onClick={() => onDelete(row)}>
                Delete
              </button>
            )}
          </div>
          <p className="field-hint">
            {row.hidden ? "Hidden: left out of the lists you pick an account from. " : ""}
            {deletable ? "It has no transactions." : row.inUse ? IN_USE : FIRST_OF_EACH}
          </p>
        </div>
      )}
    </li>
  );
};

export default AccountRowItem;
