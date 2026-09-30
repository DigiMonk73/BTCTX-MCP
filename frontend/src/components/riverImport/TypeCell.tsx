import React from "react";
import { DEPOSIT_SOURCES, WITHDRAWAL_PURPOSES, typeChange, type EditableRow } from "../../utils/riverImport";
import RiverSelect from "./RiverSelect";

interface TypeCellProps {
  row: EditableRow;
  editable: boolean;
  loading: boolean;
  onChange: (patch: Partial<EditableRow>) => void;
}

/** The row's type, a choice when River's row can be read more than one way,
 * with a withdrawal's purpose or a deposit's source. */
const TypeCell: React.FC<TypeCellProps> = ({ row, editable, loading, onChange }) => {
  const choices = row.proposal.type_choices;
  const choosable = choices.length > 1 && editable;
  return (
    <td>
      {choosable ? (
        <RiverSelect label="Transaction type" value={row.type} choices={choices} disabled={loading}
          onChange={(type) => onChange(typeChange(row, type))} />
      ) : (
        row.type
      )}
      {row.type === "Withdrawal" && choosable && (
        <RiverSelect label="Withdrawal purpose" value={row.purpose} choices={WITHDRAWAL_PURPOSES} disabled={loading}
          onChange={(purpose) => onChange({ purpose })} />
      )}
      {row.type === "Deposit" && choosable && (
        <RiverSelect label="Deposit source" value={row.source} choices={DEPOSIT_SOURCES} disabled={loading}
          onChange={(source) => onChange({ source })} />
      )}
    </td>
  );
};

export default TypeCell;
