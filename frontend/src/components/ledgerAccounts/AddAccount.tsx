import React, { useState } from "react";
import { ADD_1099DA_QUESTION, ADD_LABEL, SWITCH_HELP, addHelp, pooledNote, type YourKind } from "../../utils/ledgerAccounts";

interface AddAccountProps {
  id: string;
  kind: YourKind;
  book: AccountBook;
  busy: boolean;
  /** Sends the new account (an exchange with its 1099-DA answer); true once the server made it. */
  onAdd: (kind: YourKind, name: string, sends1099da?: boolean) => Promise<boolean>;
  onClose: () => void;
}

/** One kind's "Add a …" (5.9): the name, its help text and Q5's note, for an
 * exchange whether it sends a Form 1099-DA (#708: answered before any of its
 * sales is saved, Yes as the switch's default), Add and Cancel. The name goes
 * as typed: the server cleans it and says what it refuses. */
const AddAccount: React.FC<AddAccountProps> = ({ id, kind, book, busy, onAdd, onClose }) => {
  const [name, setName] = useState("");
  const [sends1099da, setSends1099da] = useState(true);
  const field = `ledger-add-${kind}`;
  const help = addHelp(kind, name);
  const note = pooledNote(book, kind);
  const exchange = kind === "exchange";

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (await onAdd(kind, name, exchange ? sends1099da : undefined)) onClose();
  };

  return (
    <form id={id} className="ledger-add-form" aria-label={ADD_LABEL[kind]} onSubmit={submit}>
      <div className="field">
        <label htmlFor={field}>Name</label>
        <input id={field} className="input" value={name} autoFocus autoComplete="off" spellCheck={false}
          onChange={(e) => setName(e.target.value)} aria-describedby={help ? `${field}-help` : undefined} />
        {help && <p id={`${field}-help`} className="field-hint">{help}</p>}
      </div>
      {exchange && (
        <fieldset className="ledger-add-question" aria-describedby={`${field}-1099da-help`}>
          <legend className="field-label">{ADD_1099DA_QUESTION}</legend>
          <div className="ledger-add-answers">
            {([["Yes", true], ["No", false]] as const).map(([answer, on]) => (
              <label key={answer}>
                <input type="radio" name={`${field}-1099da`} checked={sends1099da === on}
                  onChange={() => setSends1099da(on)} />
                {answer}
              </label>
            ))}
          </div>
          <p id={`${field}-1099da-help`} className="field-hint">{SWITCH_HELP}</p>
        </fieldset>
      )}
      {note && <p className="note note-warning" role="note">{note}</p>}
      <div className="ledger-add-actions">
        <button type="submit" className="btn btn-primary btn-sm" disabled={busy}>Add</button>
        <button type="button" className="btn btn-secondary btn-sm" onClick={onClose}>Cancel</button>
      </div>
    </form>
  );
};

export default AddAccount;
