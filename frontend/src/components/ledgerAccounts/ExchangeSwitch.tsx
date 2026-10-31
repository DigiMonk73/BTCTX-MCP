import React from "react";
import { SWITCH_HELP, SWITCH_LABEL } from "../../utils/ledgerAccounts";

interface ExchangeSwitchProps {
  /** For its label's and help text's ids. */
  rowKey: string;
  on: boolean;
  busy: boolean;
  onChange: (on: boolean) => void;
}

/** An exchange's "This exchange sends me a Form 1099-DA" (5.9). It moves the
 * Form 8949 boxes of its sales, past years' too, so the change goes through
 * the past-year warning (5.8); the box shows what's saved, never what's asked. */
const ExchangeSwitch: React.FC<ExchangeSwitchProps> = ({ rowKey, on, busy, onChange }) => {
  const id = `ledger-1099da-${rowKey}`;
  return (
    <div className="ledger-switch">
      <input id={id} type="checkbox" checked={on} disabled={busy} aria-describedby={`${id}-help`}
        onChange={(e) => onChange(e.target.checked)} />
      <span className="ledger-switch-text">
        <label htmlFor={id}>{SWITCH_LABEL}</label>
        <span id={`${id}-help`} className="field-hint">{SWITCH_HELP}</span>
      </span>
    </div>
  );
};

export default ExchangeSwitch;
