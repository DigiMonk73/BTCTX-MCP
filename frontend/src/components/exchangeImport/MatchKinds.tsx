import React from "react";
import { KIND_CHOICES, kindOf } from "../../utils/exchangeMapping";

interface MatchKindsProps {
  words: string[];
  kinds: Record<string, MappingKind | "">;
  disabled: boolean;
  onChange: (word: string, kind: MappingKind | "") => void;
}

/** What each of the kind column's words means. A word left unchosen
 * leaves its rows out, and the preview says which. */
const MatchKinds: React.FC<MatchKindsProps> = ({ words, kinds, disabled, onChange }) => (
  <fieldset className="match-group">
    <legend>What each kind of row is</legend>
    <p className="field-hint">A word left on “Choose” is left out of the import, and the preview names its rows.</p>
    <div className="match-grid">
      {words.map((word, i) => (
        <div className="field" key={word}>
          <label htmlFor={`match-kind-${i}`}>“{word}” is</label>
          <select id={`match-kind-${i}`} className="input" value={kindOf(kinds, word)} disabled={disabled}
            onChange={(e) => onChange(word, e.target.value as MappingKind | "")}>
            <option value="">Choose</option>
            {KIND_CHOICES.map((c) => <option key={c.kind} value={c.kind}>{c.label}</option>)}
          </select>
        </div>
      ))}
    </div>
  </fieldset>
);

export default MatchKinds;
