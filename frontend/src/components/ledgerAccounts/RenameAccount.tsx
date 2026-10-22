import React, { useState } from "react";
import { addHelp } from "../../utils/ledgerAccounts";

interface RenameAccountProps {
  account: LedgerAccount;
  busy: boolean;
  /** Sends the new nickname; true once the server took it. */
  onRename: (account: LedgerAccount, name: string) => Promise<boolean>;
  onClose: () => void;
}

/** An account's Rename (5.9, B8-5n): the Nickname field, filled with the nickname
 * it has (an exchange's account: its exchange's, which names both), Save and Cancel.
 * The name goes as typed: the server trims it and says what it refuses. */
const RenameAccount: React.FC<RenameAccountProps> = ({ account, busy, onRename, onClose }) => {
  const [name, setName] = useState(account.exchange ?? account.name);
  // Renaming an exchange renames both its accounts: say how they'll be called
  const help = account.kind === "exchange" ? addHelp("exchange", name) : null;

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (await onRename(account, name)) onClose();
  };

  return (
    <form className="ledger-add-form" aria-label={`Rename ${account.name}`} onSubmit={submit}>
      <input className="input" aria-label="Nickname" value={name} onChange={(e) => setName(e.target.value)} />
      {help && <p className="settings-option-subtitle">{help}</p>}
      <div className="ledger-account-actions">
        <button type="submit" className="btn btn-primary btn-sm" disabled={busy}>Save</button>
        <button type="button" className="btn btn-secondary btn-sm" onClick={onClose}>Cancel</button>
      </div>
    </form>
  );
};

export default RenameAccount;
