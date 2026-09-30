import React from "react";

interface RiverSelectProps {
  label: string;
  value: string;
  choices: string[];
  disabled: boolean;
  onChange: (value: string) => void;
}

/** A choice in a River preview row: the type, a withdrawal's purpose or a
 * deposit's source. */
const RiverSelect: React.FC<RiverSelectProps> = ({ label, value, choices, disabled, onChange }) => (
  <select
    value={value}
    disabled={disabled}
    onChange={(e) => onChange(e.target.value)}
    className="input input-sm river-select"
    aria-label={label}
  >
    {choices.map((choice) => (
      <option key={choice} value={choice}>{choice}</option>
    ))}
  </select>
);

export default RiverSelect;
