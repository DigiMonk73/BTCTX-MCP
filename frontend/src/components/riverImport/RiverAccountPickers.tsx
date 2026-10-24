import React from "react";
import type { RiverChoice, RiverChoices, RiverPick } from "../../utils/riverImport";

interface RiverAccountPickersProps {
  choices: RiverChoices;
  chosen: RiverPick;
  disabled: boolean;
  onChange: (pick: RiverPick) => void;
}

interface PickerProps {
  id: string;
  label: string;
  hint: string;
  blank: string;
  choices: RiverChoice[];
  value: number | undefined;
  disabled: boolean;
  onChange: (id: number) => void;
}

/** One of the two: a blank first only while none is chosen (every one hidden), so none is taken unasked. */
const Picker: React.FC<PickerProps> = ({ id, label, hint, blank, choices, value, disabled, onChange }) => (
  <div className="field">
    <label htmlFor={id}>{label}</label>
    <select id={id} className="input" value={value ?? ""} disabled={disabled} required
      aria-describedby={`${id}-hint`} onChange={(e) => onChange(Number(e.target.value))}>
      {value === undefined && <option value="" disabled>{blank}</option>}
      {choices.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
    </select>
    <p id={`${id}-hint`} className="field-hint">{hint}</p>
  </div>
);

/** River's "Exchange" and "Wallet for sends and receives" (2.0 spec 5.11,
 * 5.13, Q8): asked once per file when there's more than one of either, the
 * first shown one chosen; with one of each, nothing shows. */
const RiverAccountPickers: React.FC<RiverAccountPickersProps> = ({ choices, chosen, disabled, onChange }) => {
  if (!choices.askExchange && !choices.askWallet) return null;
  return (
    <div className="river-accounts" role="group" aria-label="This file's accounts">
      {choices.askExchange && (
        <Picker id="river-exchange" label="Exchange" blank="Choose an exchange"
          hint="The exchange this file is from: its buys, sells and balances go there."
          choices={choices.exchanges} value={chosen.exchange} disabled={disabled}
          onChange={(exchange) => onChange({ ...chosen, exchange })} />
      )}
      {choices.askWallet && (
        <Picker id="river-wallet" label="Wallet for sends and receives" blank="Choose a wallet"
          hint="River's sends to your wallet go into it, and its receives come from it."
          choices={choices.wallets} value={chosen.wallet} disabled={disabled}
          onChange={(wallet) => onChange({ ...chosen, wallet })} />
      )}
    </div>
  );
};

export default RiverAccountPickers;
