import React from "react";

interface ExchangeFileRowProps {
  /** The mapping's name: River's file keeps River's own words. */
  name: string;
  river: boolean;
  /** Whether Preview can be clicked: a file chosen, its accounts and columns known. */
  canPreview: boolean;
  /** What Preview waits for, said under it (#773): "Choose the exchange first." */
  waitingFor?: string;
  /** The file is being read for its first preview. */
  processing: boolean;
  /** A preview or an import is on its way: another file waits. */
  busy: boolean;
  onFile: (file: File | null) => void;
  onPreview: () => void;
}

/** The import's file and its Preview button. */
const ExchangeFileRow: React.FC<ExchangeFileRowProps> = ({
  name, river, canPreview, waitingFor, processing, busy, onFile, onPreview,
}) => (
  <div className="settings-option">
    <div className="option-info">
      <span className="settings-option-title">{river ? "River Bitcoin Activity CSV" : `${name} CSV`}</span>
      <p className="settings-option-subtitle">
        {river && <>Download your Bitcoin activity CSV from river.com → profile icon → Documents → Statements → Custom,
          then upload it here. </>}
        Transactions already in your ledger are found and left out, so overlapping date ranges can be imported
        again.
      </p>
    </div>
    <div className="river-file-controls">
      <div className="river-input-row">
        <input
          type="file"
          id="river-csv-input"
          aria-label={`${name} CSV file`}
          accept=".csv"
          disabled={busy}
          onChange={(e) => onFile(e.target.files?.[0] ?? null)}
          className="csv-file-input"
        />
        <button onClick={onPreview} disabled={!canPreview} className="btn btn-secondary"
          aria-describedby={waitingFor ? "river-preview-waiting" : undefined}>
          {processing ? "Processing..." : "Preview"}
        </button>
      </div>
      {waitingFor && <p id="river-preview-waiting" className="field-hint" role="status">{waitingFor}</p>}
    </div>
  </div>
);

export default ExchangeFileRow;
