import React, { useState } from "react";
import { addHelp, pooledNote, type YourKind } from "../../utils/ledgerAccounts";

const ADD_LABEL: Record<YourKind, string> = {
  wallet: "Add a wallet",
  exchange: "Add an exchange",
  bank: "Add a bank",
};

interface AddAccountProps {
  kind: YourKind;
  book: AccountBook;
  busy: boolean;
  /** Sends the new account; true once the server made it. */
  onAdd: (kind: YourKind, name: string) => Promise<boolean>;
}

/** One kind's "Add a …" (5.9): the Nickname field, its help text and Q5's note, Add and Cancel. */
const AddAccount: React.FC<AddAccountProps> = ({ kind, book, busy, onAdd }) => {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const help = addHelp(kind, name);
  const note = pooledNote(book, kind);

  const close = () => {
    setOpen(false);
    setName("");
  };

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (await onAdd(kind, name)) close();
  };

  if (!open) {
    return (
      <button type="button" className="btn btn-secondary btn-sm" disabled={busy} onClick={() => setOpen(true)}>
        {ADD_LABEL[kind]}
      </button>
    );
  }

  return (
    <form className="ledger-add-form" aria-label={ADD_LABEL[kind]} onSubmit={submit}>
      <input className="input" aria-label="Nickname" value={name} onChange={(e) => setName(e.target.value)} />
      {help && <p className="settings-option-subtitle">{help}</p>}
      {note && <p className="note">{note}</p>}
      <div className="ledger-account-actions">
        <button type="submit" className="btn btn-primary btn-sm" disabled={busy}>Add</button>
        <button type="button" className="btn btn-secondary btn-sm" onClick={close}>Cancel</button>
      </div>
    </form>
  );
};

export default AddAccount;
