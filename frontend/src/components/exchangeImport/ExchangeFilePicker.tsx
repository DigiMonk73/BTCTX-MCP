import React from "react";
import { MATCH_COLUMNS } from "../../utils/exchangeMapping";

// Until the list is read: River, whose file the import always read
const RIVER_ONLY: ExchangeMapping[] = [{ id: "river", name: "River", ready_made: true, help: "", checked: true }];

interface ExchangeFilePickerProps {
  mappings: ExchangeMapping[] | undefined;
  value: string;
  disabled: boolean;
  onChange: (id: string) => void;
}

/** Which exchange's file it is (B5b, #567): a ready-made mapping, one of
 * the owner's own, or another exchange's, whose columns they match. */
const ExchangeFilePicker: React.FC<ExchangeFilePickerProps> = ({ mappings, value, disabled, onChange }) => {
  const listed = mappings ?? RIVER_ONLY;
  const ready = listed.filter((m) => m.ready_made);
  const own = listed.filter((m) => !m.ready_made);
  const chosen = listed.find((m) => m.id === value);
  const hint = value === MATCH_COLUMNS
    ? "Choose the file, then say which of its columns holds what: you can save it for next time."
    : chosen?.ready_made ? chosen.help : "Your own mapping. Choose the file to preview it, or to change the mapping.";
  const unchecked = chosen?.ready_made && !chosen.checked;
  return (
    <div className="field">
      <label htmlFor="exchange-file">Exchange file</label>
      <select id="exchange-file" className="input" value={value} disabled={disabled}
        aria-describedby={unchecked ? "exchange-file-hint exchange-file-unchecked" : "exchange-file-hint"}
        onChange={(e) => onChange(e.target.value)}>
        {ready.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
        {own.length > 0 && (
          <optgroup label="Your mappings">
            {own.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
          </optgroup>
        )}
        {mappings && <option value={MATCH_COLUMNS}>Another exchange: match its columns</option>}
      </select>
      {hint && <p id="exchange-file-hint" className="field-hint">{hint}</p>}
      {unchecked && (
        <p id="exchange-file-unchecked" className="field-warning">
          Read as {chosen.name} publishes its file, not yet checked against a real one: check the preview's
          rows against your file before you import them.
        </p>
      )}
    </div>
  );
};

export default ExchangeFilePicker;
