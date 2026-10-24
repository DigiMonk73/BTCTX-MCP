import React from "react";
import { ROLES, type Draft, type Role } from "../../utils/exchangeMapping";

interface MatchColumnsProps {
  columns: string[];
  draft: Draft;
  disabled: boolean;
  onChange: (role: Role, column: string) => void;
}

/** Which of the file's columns holds each thing the importer reads. */
const MatchColumns: React.FC<MatchColumnsProps> = ({ columns, draft, disabled, onChange }) => (
  <fieldset className="match-group">
    <legend>The file's columns</legend>
    <div className="match-grid">
      {ROLES.map(({ role, label, hint, required }) => (
        <div className="field" key={role}>
          <label htmlFor={`match-${role}`}>{label}{required ? "" : " (if any)"}</label>
          <select id={`match-${role}`} className="input" value={draft.columns[role] ?? ""} disabled={disabled}
            aria-describedby={`match-${role}-hint`} onChange={(e) => onChange(role, e.target.value)}>
            <option value="">{required ? "Choose a column" : "None"}</option>
            {columns.filter(Boolean).map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <p id={`match-${role}-hint`} className="field-hint">{hint}</p>
        </div>
      ))}
    </div>
  </fieldset>
);

export default MatchColumns;
