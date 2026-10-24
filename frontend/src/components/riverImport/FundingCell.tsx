import React from "react";
import type { EditableRow } from "../../utils/riverImport";
import RiverSelect from "./RiverSelect";

interface FundingCellProps {
  row: EditableRow;
  editable: boolean;
  loading: boolean;
  onChange: (patch: Partial<EditableRow>) => void;
}

/** From, then "→ To" under it, with a choice of the account a Buy was paid
 * from when River's row doesn't say: two side by side, as with one bank;
 * more (every bank, and the file's exchange's dollars, 5.11) in a list. */
const FundingCell: React.FC<FundingCellProps> = ({ row, editable, loading, onChange }) => {
  const choices = row.proposal.funding_choices;
  const choose = (acct: string) => onChange({ fromAccount: acct });
  let from: React.ReactNode = row.fromAccount;
  if (choices.length > 2 && editable) {
    from = <RiverSelect label="Buy funding source" value={row.fromAccount} choices={choices} disabled={loading}
      onChange={choose} />;
  } else if (choices.length > 1 && editable) {
    from = (
      <span className="segmented river-funding-toggle" role="group" aria-label="Buy funding source">
        {choices.map((acct) => (
          <button key={acct} type="button" disabled={loading} onClick={() => choose(acct)}
            className={row.fromAccount === acct ? "active" : undefined} aria-pressed={row.fromAccount === acct}>
            {acct}
          </button>
        ))}
      </span>
    );
  }
  return (
    <td className="river-cell-accounts">
      <span className="river-stack">
        {from}
        <span className="river-funding-dest">→ {row.toAccount}</span>
      </span>
    </td>
  );
};

export default FundingCell;
