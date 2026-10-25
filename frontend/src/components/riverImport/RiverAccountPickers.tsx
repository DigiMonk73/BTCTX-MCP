import React from "react";
import type { RiverChoices, RiverPick } from "../../utils/riverImport";
import RiverAccountPicker from "./RiverAccountPicker";

interface RiverAccountPickersProps {
  /** Undefined until the book is read: nothing to ask yet. */
  choices: RiverChoices | undefined;
  chosen: RiverPick;
  disabled: boolean;
  /** The preview was dropped: it no longer matched the pick. */
  outOfDate: boolean;
  onChange: (pick: RiverPick) => void;
}

/** River's "Exchange" and "Wallet for sends and receives" (2.0 spec 5.11,
 * 5.13, Q8): asked once per file when there's more than one of either, the
 * first shown one chosen; with one of each, nothing shows. */
const RiverAccountPickers: React.FC<RiverAccountPickersProps> = ({ choices, chosen, disabled, outOfDate, onChange }) => (
  <>
    {choices && (choices.askExchange || choices.askWallet) && (
      <div className="river-accounts" role="group" aria-label="This file's accounts">
        {choices.askExchange && (
          <RiverAccountPicker id="river-exchange" label="Exchange" blank="Choose an exchange"
            hint="The exchange this file is from: its buys, sells and balances go there."
            choices={choices.exchanges} value={chosen.exchange} disabled={disabled}
            onChange={(exchange) => onChange({ ...chosen, exchange })} />
        )}
        {choices.askWallet && (
          <RiverAccountPicker id="river-wallet" label="Wallet for sends and receives" blank="Choose a wallet"
            hint="This file's sends to your wallet go into it, and its receives come from it."
            choices={choices.wallets} value={chosen.wallet} disabled={disabled}
            onChange={(wallet) => onChange({ ...chosen, wallet })} />
        )}
      </div>
    )}
    {outOfDate && (
      <p className="note note-warning" role="status">
        The preview was made with another exchange or wallet: preview the file again.
      </p>
    )}
  </>
);

export default RiverAccountPickers;
