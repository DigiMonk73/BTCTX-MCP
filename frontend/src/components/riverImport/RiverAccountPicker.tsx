import React from "react";
import type { RiverChoice } from "../../utils/riverImport";

interface RiverAccountPickerProps {
  id: string;
  label: string;
  hint: string;
  blank: string;
  choices: RiverChoice[];
  value: number | undefined;
  disabled: boolean;
  onChange: (id: number) => void;
}

/** River's exchange or wallet: a blank first only while none is chosen (every
 * one hidden), so none is taken unasked; a hidden one says so. */
const RiverAccountPicker: React.FC<RiverAccountPickerProps> = ({ id, label, hint, blank, choices, value, disabled, onChange }) => (
  <div className="field">
    <label htmlFor={id}>{label}</label>
    <select id={id} className="input" value={value ?? ""} disabled={disabled} required
      aria-describedby={`${id}-hint`} onChange={(e) => onChange(Number(e.target.value))}>
      {value === undefined && <option value="" disabled>{blank}</option>}
      {choices.map((c) => <option key={c.id} value={c.id}>{c.hidden ? `${c.name} (hidden)` : c.name}</option>)}
    </select>
    <p id={`${id}-hint`} className="field-hint">{hint}</p>
  </div>
);

export default RiverAccountPicker;
