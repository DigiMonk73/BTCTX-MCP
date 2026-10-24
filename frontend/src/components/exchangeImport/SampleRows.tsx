import React from "react";

/** The file's header and first rows, as the importer found them. */
const SampleRows: React.FC<{ file: FileColumnsResponse }> = ({ file }) => (
  <div className="table-scroll match-samples">
    <table className="table" aria-label="The file's first rows">
      <caption className="field-hint">Row {file.header_row} of the file names its columns.</caption>
      <thead>
        <tr>{file.columns.map((c, i) => <th key={i} scope="col">{c}</th>)}</tr>
      </thead>
      <tbody>
        {file.samples.map((row, i) => (
          <tr key={i}>{file.columns.map((_c, j) => <td key={j}>{row[j] ?? ""}</td>)}</tr>
        ))}
      </tbody>
    </table>
  </div>
);

export default SampleRows;
