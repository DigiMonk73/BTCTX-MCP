import React, { useState } from "react";
import { ADD_LABEL, addHelp, pooledNote, type YourKind } from "../../utils/ledgerAccounts";

interface AddAccountProps {
  id: string;
  kind: YourKind;
  book: AccountBook;
  busy: boolean;
  /** Sends the new account; true once the server made it. */
  onAdd: (kind: YourKind, name: string) => Promise<boolean>;
  onClose: () => void;
}

/** One kind's "Add a …" (5.9): the name, its help text and Q5's note, Add and
 * Cancel. The name goes as typed: the server cleans it and says what it refuses. */
const AddAccount: React.FC<AddAccountProps> = ({ id, kind, book, busy, onAdd, onClose }) => {
  const [name, setName] = useState("");
  const field = `ledger-add-${kind}`;
  const help = addHelp(kind, name);
  const note = pooledNote(book, kind);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (await onAdd(kind, name)) onClose();
  };

  return (
    <form id={id} className="ledger-add-form" aria-label={ADD_LABEL[kind]} onSubmit={submit}>
      <div className="field">
        <label htmlFor={field}>Name</label>
        <input id={field} className="input" value={name} autoFocus autoComplete="off" spellCheck={false}
          onChange={(e) => setName(e.target.value)} aria-describedby={help ? `${field}-help` : undefined} />
        {help && <p id={`${field}-help`} className="field-hint">{help}</p>}
      </div>
      {note && <p className="note note-warning" role="note">{note}</p>}
      <div className="ledger-add-actions">
        <button type="submit" className="btn btn-primary btn-sm" disabled={busy}>Add</button>
        <button type="button" className="btn btn-secondary btn-sm" onClick={onClose}>Cancel</button>
      </div>
    </form>
  );
};

export default AddAccount;
