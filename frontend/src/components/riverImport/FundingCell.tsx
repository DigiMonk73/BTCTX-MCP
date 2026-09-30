import React from "react";
import type { EditableRow } from "../../utils/riverImport";

interface FundingCellProps {
  row: EditableRow;
  editable: boolean;
  loading: boolean;
  onChange: (patch: Partial<EditableRow>) => void;
}

/** From → To, with a choice of the account a Buy was paid from when River's
 * row doesn't say. */
const FundingCell: React.FC<FundingCellProps> = ({ row, editable, loading, onChange }) => (
  <td className="river-cell-accounts">
    {row.proposal.funding_choices.length > 1 && editable ? (
      <span className="segmented river-funding-toggle" role="group" aria-label="Buy funding source">
        {row.proposal.funding_choices.map((acct) => (
          <button
            key={acct}
            type="button"
            disabled={loading}
            className={row.fromAccount === acct ? "active" : undefined}
            aria-pressed={row.fromAccount === acct}
            onClick={() => onChange({ fromAccount: acct })}
          >
            {acct}
          </button>
        ))}
        <span className="river-funding-dest">→ {row.toAccount}</span>
      </span>
    ) : (
      `${row.fromAccount} → ${row.toAccount}`
    )}
  </td>
);

export default FundingCell;
