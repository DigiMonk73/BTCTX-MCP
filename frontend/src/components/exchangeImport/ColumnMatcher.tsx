// The column matcher (B5b, #567): another exchange's file matched once,
// then saved as the owner's own mapping. It says how to read the file,
// never where its rows go: the exchange and the wallet are chosen apart.

import React from "react";
import { missingRoles, withKind, type Draft, type Role } from "../../utils/exchangeMapping";
import MatchColumns from "./MatchColumns";
import MatchFormat from "./MatchFormat";
import MatchKinds from "./MatchKinds";
import MatchWords from "./MatchWords";
import SampleRows from "./SampleRows";

interface ColumnMatcherProps {
  file: FileColumnsResponse;
  draft: Draft;
  disabled: boolean;
  saving: boolean;
  onChange: (draft: Draft) => void;
  onSave: () => void;
}

const ColumnMatcher: React.FC<ColumnMatcherProps> = ({ file, draft, disabled, saving, onChange, onSave }) => {
  const missing = missingRoles(draft);
  const wordsOf = (role: Role) => (draft.columns[role] ? file.values[draft.columns[role] as string] ?? [] : []);
  // The import reads a kind word in any case, so each is asked once ("Buy" for "BUY" too)
  const kindWords = wordsOf("kind").filter((w, i, all) => all.findIndex((v) => v.toLowerCase() === w.toLowerCase()) === i);
  const setColumn = (role: Role, column: string) => onChange({ ...draft, columns: { ...draft.columns, [role]: column } });
  return (
    <div className="column-matcher">
      <SampleRows file={file} />
      <MatchColumns columns={file.columns} draft={draft} disabled={disabled} onChange={setColumn} />
      {draft.columns.kind && (
        <MatchKinds words={kindWords} kinds={draft.kinds} disabled={disabled}
          onChange={(word, kind) => onChange({ ...draft, kinds: withKind(draft.kinds, word, kind) })} />
      )}
      {draft.columns.asset && (
        <MatchWords legend="Bitcoin's asset" hint="The rows of any other asset are left out." words={wordsOf("asset")}
          chosen={draft.btcAssets} disabled={disabled} onChange={(btcAssets) => onChange({ ...draft, btcAssets })} />
      )}
      {draft.columns.status && (
        <MatchWords legend="A completed row's status" hint="The rows of any other status are left out; with none ticked, every row is read."
          words={wordsOf("status")} chosen={draft.done} disabled={disabled} onChange={(done) => onChange({ ...draft, done })} />
      )}
      <MatchFormat draft={draft} disabled={disabled} onChange={(patch) => onChange({ ...draft, ...patch })} />
      {missing.length > 0 && (
        <p className="note note-warning" role="status">Still to match: {missing.map((m) => m.label).join(", ")}.</p>
      )}
      <div className="field match-save">
        <label htmlFor="match-name">Mapping's name</label>
        <div className="river-input-row">
          <input id="match-name" className="input" value={draft.name} maxLength={60} disabled={disabled}
            onChange={(e) => onChange({ ...draft, name: e.target.value })} placeholder="The exchange's name" />
          <button type="button" className="btn btn-secondary" onClick={onSave}
            disabled={disabled || saving || missing.length > 0 || !draft.name.trim()}>
            {saving ? "Saving..." : "Save this mapping"}
          </button>
        </div>
        <p className="field-hint">Saved, it's in the list of exchange files next time. You can preview without saving.</p>
      </div>
    </div>
  );
};

export default ColumnMatcher;
