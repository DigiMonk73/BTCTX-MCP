import React from "react";
import { formatLocalDateTime } from "../../utils/format";
import { STATUS_LABEL, type EditableRow } from "../../utils/riverImport";
import BasisCell from "./BasisCell";
import FundingCell from "./FundingCell";
import TypeCell from "./TypeCell";

interface RiverRowProps {
  row: EditableRow;
  loading: boolean;
  onChange: (patch: Partial<EditableRow>) => void;
}

/** One row of the River preview. A row already in the ledger can't be
 * changed or imported. */
const RiverRow: React.FC<RiverRowProps> = ({ row, loading, onChange }) => {
  const p = row.proposal;
  const isMatched = p.status === "matched";
  const cell = { row, editable: !isMatched, loading, onChange };
  return (
    <tr className={isMatched ? "river-row-matched" : undefined}>
      <td className="river-col-include">
        <input
          type="checkbox"
          checked={row.include}
          disabled={isMatched || loading}
          onChange={(e) => onChange({ include: e.target.checked })}
          aria-label={`Include row ${p.row_number}`}
        />
      </td>
      <td>
        <span className={`river-status river-status-${p.status}`}>
          {STATUS_LABEL[p.status]}
        </span>
      </td>
      <td className="river-cell-date">{formatLocalDateTime(p.date)}</td>
      <TypeCell {...cell} />
      <FundingCell {...cell} />
      <td className="river-cell-num">{p.amount} BTC</td>
      <BasisCell {...cell} />
      <td className="river-cell-num">
        {p.proceeds_usd ? `$${p.proceeds_usd}` : "—"}
      </td>
      <td className="river-cell-num">
        {row.type === "Transfer" && !isMatched ? (
          <input
            type="text"
            inputMode="decimal"
            value={row.feeAmount}
            disabled={loading}
            onChange={(e) => onChange({ feeAmount: e.target.value })}
            className="input input-sm river-num-input"
            placeholder="0"
            aria-label="Fee (BTC)"
          />
        ) : (
          row.feeAmount || "—"
        )}
      </td>
    </tr>
  );
};

export default RiverRow;
