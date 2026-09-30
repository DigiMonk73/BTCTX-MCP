import React from "react";
import type { EditableRow } from "../../utils/riverImport";

interface BasisCellProps {
  row: EditableRow;
  editable: boolean;
  loading: boolean;
  onChange: (patch: Partial<EditableRow>) => void;
}

/** The cost basis, editable on a deposit and marked "est." while it is
 * still the value filled from the day's price. */
const BasisCell: React.FC<BasisCellProps> = ({ row, editable, loading, onChange }) => {
  const p = row.proposal;
  return (
    <td className="river-cell-num">
      {row.type === "Deposit" && editable ? (
        <span className="river-basis-edit">
          $
          <input
            type="text"
            inputMode="decimal"
            value={row.costBasisUsd}
            disabled={loading}
            onChange={(e) => onChange({ costBasisUsd: e.target.value })}
            className="input input-sm river-num-input"
            aria-label="Cost basis (USD)"
          />
          {p.basis_autofilled && row.costBasisUsd === String(p.cost_basis_usd) && (
            <span className="river-autofill" title="Estimated from the historical BTC price — edit if you know the exact value">
              est.
            </span>
          )}
        </span>
      ) : (
        row.costBasisUsd ? `$${row.costBasisUsd}` : "—"
      )}
    </td>
  );
};

export default BasisCell;
