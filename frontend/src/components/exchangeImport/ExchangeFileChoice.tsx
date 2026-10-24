// Which exchange's file the import reads, and for another exchange's (or
// one of the owner's saved mappings) the column matcher (B5b, #567).

import React from "react";
import { mappingFrom, type Draft } from "../../utils/exchangeMapping";
import type { ExchangeFile } from "../../utils/useExchangeFile";
import ColumnMatcher from "./ColumnMatcher";
import { MATCH_COLUMNS } from "../../utils/exchangeMapping";
import ExchangeFilePicker from "./ExchangeFilePicker";
import "../../styles/exchangeImport.css";

interface ExchangeFileChoiceProps {
  exchange: ExchangeFile;
  file: File | null;
  disabled: boolean;
  /** Another mapping was chosen: a preview made with the old one is out of date. */
  onMappingChanged: () => void;
}

/** Whether a draft reads the file another way than the one before: its name alone doesn't. */
const readsOtherwise = (before: Draft, after: Draft) =>
  JSON.stringify(mappingFrom({ ...before, name: "" })) !== JSON.stringify(mappingFrom({ ...after, name: "" }));

const ExchangeFileChoice: React.FC<ExchangeFileChoiceProps> = ({ exchange, file, disabled, onMappingChanged }) => {
  const choose = (id: string) => {
    onMappingChanged();
    void exchange.choose(id, file);
  };
  // A file matched by hand whose columns are a ready-made mapping's
  const looksLike = exchange.chosenId === MATCH_COLUMNS && exchange.columns?.looks_like
    ? exchange.mappings?.find((m) => m.id === exchange.columns?.looks_like) : undefined;
  const ownChosen = exchange.matching && exchange.chosenId !== MATCH_COLUMNS;
  const removeIt = () => {
    if (window.confirm(`Delete your mapping “${exchange.chosen?.name ?? ""}”? Its files can still be matched again.`)) {
      onMappingChanged();
      void exchange.remove();
    }
  };
  return (
    <div className="exchange-file-choice">
      <ExchangeFilePicker mappings={exchange.mappings} value={exchange.chosenId} disabled={disabled} onChange={choose} />
      {looksLike && (
        <p className="note" role="note">
          This looks like {looksLike.name}'s file.{" "}
          <button type="button" className="btn btn-secondary btn-sm" disabled={disabled}
            onClick={() => choose(looksLike.id)}>
            Read it as {looksLike.name}'s
          </button>
        </p>
      )}
      {exchange.matching && exchange.columns && (
        <ColumnMatcher file={exchange.columns} draft={exchange.draft} disabled={disabled} saving={exchange.saving}
          onChange={(draft) => {
            if (readsOtherwise(exchange.draft, draft)) onMappingChanged();
            exchange.setDraft(draft);
          }}
          onSave={() => void exchange.save()} />
      )}
      {ownChosen && (
        <button type="button" className="btn btn-danger btn-sm" disabled={disabled} onClick={removeIt}>
          Delete this mapping
        </button>
      )}
    </div>
  );
};

export default ExchangeFileChoice;
