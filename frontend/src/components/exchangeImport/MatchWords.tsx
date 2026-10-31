import React from "react";

interface MatchWordsProps {
  legend: string;
  hint: string;
  words: string[];
  chosen: string[];
  disabled: boolean;
  onChange: (chosen: string[]) => void;
}

/** Which of a column's words count (bitcoin's asset, a completed row's
 * status), each a checkbox. */
const MatchWords: React.FC<MatchWordsProps> = ({ legend, hint, words, chosen, disabled, onChange }) => {
  const picked = new Set(chosen.map((w) => w.toLowerCase()));
  const toggle = (word: string, on: boolean) =>
    onChange(on ? [...chosen, word] : chosen.filter((w) => w.toLowerCase() !== word.toLowerCase()));
  return (
    <fieldset className="match-group">
      <legend>{legend}</legend>
      <p className="field-hint">{hint}</p>
      <div className="match-words">
        {words.map((word) => (
          <label key={word} className="match-word">
            <input type="checkbox" checked={picked.has(word.toLowerCase())} disabled={disabled}
              onChange={(e) => toggle(word, e.target.checked)} />
            {word}
          </label>
        ))}
      </div>
    </fieldset>
  );
};

export default MatchWords;
