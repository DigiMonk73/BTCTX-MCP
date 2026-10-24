import React, { useState } from "react";
import { RENAME_FILES_NOTE, renameHelp, renameReady, type AccountRow } from "../../utils/ledgerAccounts";

interface RenameAccountProps {
  row: AccountRow;
  /** A change is saving (or an exchange's switch): Rename waits. */
  busy: boolean;
  /** Sends the new name; true once the server made it. */
  onRename: (row: AccountRow, name: string) => Promise<boolean>;
}

/** A row's Rename (#356, 2.0 spec 5.9): its name, Rename, what an exchange's
 * two accounts become, and how files name a renamed account (5.11). The name
 * goes as typed: the server cleans it and says what it refuses. */
const RenameAccount: React.FC<RenameAccountProps> = ({ row, busy, onRename }) => {
  const [name, setName] = useState(row.name);
  const field = `ledger-rename-${row.key}`;
  const help = renameHelp(row, name);
  const ready = renameReady(row, name);

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (ready && !busy) void onRename(row, name);
  };

  return (
    <form className="ledger-rename" onSubmit={submit}>
      <div className="field">
        <label htmlFor={field}>Name</label>
        <div className="ledger-rename-row">
          <input id={field} className="input" value={name} autoComplete="off" spellCheck={false}
            onChange={(e) => setName(e.target.value)}
            aria-describedby={help ? `${field}-help ${field}-files` : `${field}-files`} />
          <button type="submit" className="btn btn-secondary btn-sm" disabled={busy || !ready}>Rename</button>
        </div>
        {help && <p id={`${field}-help`} className="field-hint">{help}</p>}
        <p id={`${field}-files`} className="field-hint">{RENAME_FILES_NOTE}</p>
      </div>
    </form>
  );
};

export default RenameAccount;
