import React, { useState } from "react";
import { balanceText, type AccountGroup, type AccountRow, type YourKind } from "../../utils/ledgerAccounts";
import AccountRowItem from "./AccountRowItem";
import AddAccount from "./AddAccount";

interface AccountGroupListProps {
  group: AccountGroup;
  book: AccountBook;
  balances: AccountBalance[] | undefined;
  busy: boolean;
  /** The row whose details are open, of any group: one at a time. */
  openRow: string | null;
  onToggleRow: (row: AccountRow) => void;
  onHide: (row: AccountRow, hidden: boolean) => void;
  onDelete: (row: AccountRow) => void;
  onAdd: (kind: YourKind, name: string) => Promise<boolean>;
  /** The add form closed: a refusal it got is no longer news. */
  onAddClosed: () => void;
}

/** One kind's accounts (Wallets, Exchanges or Banks): its Add button and
 * form, its rows, and the hidden ones under "Show hidden (n)". */
const AccountGroupList: React.FC<AccountGroupListProps> = ({
  group, book, balances, busy, openRow, onToggleRow, onHide, onDelete, onAdd, onAddClosed,
}) => {
  const [adding, setAdding] = useState(false);
  const [showHidden, setShowHidden] = useState(false);
  const heading = `ledger-group-${group.kind}`;
  const hiddenList = `${heading}-hidden`;
  const item = (row: AccountRow) => (
    <AccountRowItem key={row.key} row={row} balance={balanceText(row, balances)} open={openRow === row.key}
      busy={busy} onToggle={onToggleRow} onHide={onHide} onDelete={onDelete} />
  );

  return (
    <div className="ledger-group" role="group" aria-labelledby={heading}>
      <div className="ledger-group-head">
        <h4 id={heading} className="ledger-group-title">{group.title}</h4>
        {!adding && (
          <button type="button" className="btn btn-secondary btn-sm" disabled={busy} onClick={() => setAdding(true)}>
            {group.add}
          </button>
        )}
      </div>
      {adding && <AddAccount kind={group.kind} book={book} busy={busy} onAdd={onAdd}
        onClose={() => { setAdding(false); onAddClosed(); }} />}
      {group.shown.length > 0 && <ul className="ledger-account-list">{group.shown.map(item)}</ul>}
      {group.hidden.length > 0 && (
        <>
          <button type="button" className="btn btn-quiet btn-sm ledger-show-hidden" aria-expanded={showHidden}
            aria-controls={hiddenList} onClick={() => setShowHidden(!showHidden)}>
            Show hidden ({group.hidden.length})
          </button>
          {showHidden && <ul id={hiddenList} className="ledger-account-list">{group.hidden.map(item)}</ul>}
        </>
      )}
    </div>
  );
};

export default AccountGroupList;
