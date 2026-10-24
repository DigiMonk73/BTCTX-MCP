import React, { useMemo } from "react";
import { fileZones, type Draft } from "../../utils/exchangeMapping";

interface MatchFormatProps {
  draft: Draft;
  disabled: boolean;
  onChange: (patch: Partial<Draft>) => void;
}

/** How the file writes its times, dollars and numbers. */
const MatchFormat: React.FC<MatchFormatProps> = ({ draft, disabled, onChange }) => {
  const zones = useMemo(() => fileZones(), []);
  const check = (label: string, key: "buyAfterFee" | "sellAfterFee" | "sendFeeIncluded") => (
    <label className="match-word">
      <input type="checkbox" checked={draft[key]} disabled={disabled}
        onChange={(e) => onChange({ [key]: e.target.checked })} />
      {label}
    </label>
  );
  return (
    <fieldset className="match-group">
      <legend>How the file writes things</legend>
      <div className="match-grid">
        <div className="field">
          <label htmlFor="match-zone">The file's times are in</label>
          <select id="match-zone" className="input" value={draft.zone} disabled={disabled}
            aria-describedby="match-zone-hint" onChange={(e) => onChange({ zone: e.target.value })}>
            {zones.map((z) => <option key={z} value={z}>{z === "dates" ? "Each date says its own zone" : z}</option>)}
          </select>
          <p id="match-zone-hint" className="field-hint">A date that says its zone (“Z”, “+00:00”, “EST”) is read in it.</p>
        </div>
        <div className="field">
          <label htmlFor="match-numbers">Numbers are written</label>
          <select id="match-numbers" className="input" value={draft.decimalComma ? "comma" : "point"} disabled={disabled}
            onChange={(e) => onChange({ decimalComma: e.target.value === "comma" })}>
            <option value="point">1,234.56</option>
            <option value="comma">1.234,56</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="match-dates">Dates are written</label>
          <select id="match-dates" className="input" value={draft.dayFirst ? "day" : "month"} disabled={disabled}
            onChange={(e) => onChange({ dayFirst: e.target.value === "day" })}>
            <option value="month">Month first (04/01/2025 is April 1)</option>
            <option value="day">Day first (04/01/2025 is 4 January)</option>
          </select>
        </div>
      </div>
      <div className="match-words">
        {check("A buy's dollars include its fee (the total paid)", "buyAfterFee")}
        {check("A sell's dollars are after its fee (what arrived)", "sellAfterFee")}
        {check("A send's bitcoin includes its network fee", "sendFeeIncluded")}
      </div>
    </fieldset>
  );
};

export default MatchFormat;
