import React, { useEffect, useRef, useState } from "react";
import { balanceText, ledgerIds, type AccountGroup, type AccountRow, type YourKind } from "../../utils/ledgerAccounts";
import AccountRowItem from "./AccountRowItem";
import AddAccount from "./AddAccount";

interface AccountGroupListProps {
  group: AccountGroup;
  book: AccountBook;
  balances: AccountBalance[] | undefined;
  busy: boolean;
  /** An exchange's switch is saving: every other change waits. */
  switching: boolean;
  /** The row whose details are open, of any group: one at a time. */
  openRow: string | null;
  onToggleRow: (row: AccountRow) => void;
  onHide: (row: AccountRow, hidden: boolean) => void;
  onDelete: (row: AccountRow) => void;
  onSwitch1099da: (row: AccountRow, on: boolean) => void;
  onRename: (row: AccountRow, name: string) => void;
  onAdd: (kind: YourKind, name: string) => Promise<boolean>;
  /** The add form closed: a refusal it got is no longer news. */
  onAddClosed: () => void;
}

/** One kind's accounts (Wallets, Exchanges or Banks): its Add button and
 * form, its rows, and the hidden ones under "Show hidden (n)". */
const AccountGroupList: React.FC<AccountGroupListProps> = ({
  group, book, balances, busy, switching, openRow, onToggleRow, onHide, onDelete, onSwitch1099da, onRename, onAdd,
  onAddClosed,
}) => {
  const [adding, setAdding] = useState(false);
  const [showHidden, setShowHidden] = useState(false);
  const addButton = useRef<HTMLButtonElement>(null);
  const [refocus, setRefocus] = useState(false);
  const heading = ledgerIds.group(group.kind);
  const hiddenList = ledgerIds.hiddenList(group.kind);
  const addForm = ledgerIds.addForm(group.kind);
  // The last hidden one shown again: the next one hidden starts folded too
  if (showHidden && group.hidden.length === 0) setShowHidden(false);
  // The keyboard goes back to the button the form opened from, once it's
  // enabled again (a disabled button can't take focus)
  const closeAdd = () => {
    setAdding(false);
    onAddClosed();
    setRefocus(true);
  };
  useEffect(() => {
    if (!refocus || busy) return;
    addButton.current?.focus();
    setRefocus(false);
  }, [refocus, busy]);
  const item = (row: AccountRow) => (
    <AccountRowItem key={row.key} row={row} balance={balanceText(row, balances)} open={openRow === row.key}
      busy={busy} switching={switching} onToggle={onToggleRow} onHide={onHide} onDelete={onDelete}
      onSwitch1099da={onSwitch1099da} onRename={onRename} />
  );

  return (
    <div className="ledger-group" role="group" aria-labelledby={heading}>
      <div className="ledger-group-head">
        <h4 id={heading} className="ledger-group-title">{group.title}</h4>
        <button ref={addButton} id={ledgerIds.addButton(group.kind)} type="button" className="btn btn-secondary btn-sm"
          aria-expanded={adding} aria-controls={adding ? addForm : undefined} disabled={busy || switching}
          onClick={() => (adding ? closeAdd() : setAdding(true))}>
          {group.add}
        </button>
      </div>
      {adding && <AddAccount id={addForm} kind={group.kind} book={book} busy={busy} onAdd={onAdd} onClose={closeAdd} />}
      {group.shown.length > 0 && <ul className="ledger-account-list">{group.shown.map(item)}</ul>}
      {group.hidden.length > 0 && (
        <>
          <button type="button" id={ledgerIds.showHidden(group.kind)} className="btn btn-quiet btn-sm ledger-show-hidden"
            aria-expanded={showHidden} aria-controls={showHidden ? hiddenList : undefined}
            onClick={() => setShowHidden(!showHidden)}>
            Show hidden ({group.hidden.length})
          </button>
          {showHidden && <ul id={hiddenList} className="ledger-account-list">{group.hidden.map(item)}</ul>}
        </>
      )}
    </div>
  );
};

export default AccountGroupList;
