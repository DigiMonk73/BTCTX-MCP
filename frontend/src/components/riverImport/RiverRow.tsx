import React from "react";
import { STATUS_LABEL, feeText, type EditableRow } from "../../utils/riverImport";
import BasisCell from "./BasisCell";
import FundingCell from "./FundingCell";
import TypeCell from "./TypeCell";

interface RiverRowProps {
  row: EditableRow;
  loading: boolean;
  onChange: (patch: Partial<EditableRow>) => void;
}

/** One row of the River preview. A row already in the ledger starts
 * unticked; ticked, it's imported all the same and can be changed (#253). */
const RiverRow: React.FC<RiverRowProps> = ({ row, loading, onChange }) => {
  const p = row.proposal;
  const leftOut = p.status === "matched" && !row.include;
  const cell = { row, editable: !leftOut, loading, onChange };
  return (
    <tr className={leftOut ? "river-row-matched" : undefined}>
      <td className="river-col-include">
        <input
          type="checkbox"
          checked={row.include}
          disabled={loading}
          onChange={(e) => onChange({ include: e.target.checked })}
          aria-label={`Include row ${p.row_number}`}
        />
      </td>
      <td>
        <span className={`river-status river-status-${p.status}`}>
          {STATUS_LABEL[p.status]}
        </span>
      </td>
      <td className="river-cell-date">
        {new Date(p.date).toLocaleDateString()}
        <span className="river-cell-sub">
          {new Date(p.date).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}
        </span>
      </td>
      <TypeCell {...cell} />
      <FundingCell {...cell} />
      <td className="river-cell-num">{p.amount} BTC</td>
      <BasisCell {...cell} />
      <td className="river-cell-num">
        {p.proceeds_usd ? `$${p.proceeds_usd}` : "—"}
      </td>
      <td className="river-cell-num">
        {row.type === "Transfer" && !leftOut ? (
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
          feeText(row)
        )}
      </td>
    </tr>
  );
};

export default RiverRow;
