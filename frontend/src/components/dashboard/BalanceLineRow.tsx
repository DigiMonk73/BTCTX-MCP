import React, { useId } from "react";
import { listsAccounts, type BalanceLine } from "../../utils/dashboard";
import { formatBtc, formatUsd } from "../../utils/format";
import Chevron from "../Chevron";
import FigureRow from "./FigureRow";

interface BalanceLineRowProps {
  line: BalanceLine;
  open: boolean;
  onToggle: () => void;
}

/** A kind's line on Portfolio Overview (#674): its label and total, as 1.x
 * has them. Where it has accounts to list, the whole line is a button, a
 * caret (Settings' chevron) after its label, that opens them under it. */
const BalanceLineRow: React.FC<BalanceLineRowProps> = ({ line, open, onToggle }) => {
  const id = useId();
  const figure = line.currency === "USD" ? formatUsd : formatBtc;
  if (!listsAccounts(line)) {
    return <FigureRow label={line.label}>{figure(line.total)}</FigureRow>;
  }
  return (
    <>
      <p>
        <button type="button" className="balance-line-toggle chevron-toggle" aria-expanded={open} aria-controls={id} onClick={onToggle}>
          <strong>
            {line.label}
            <Chevron />
          </strong>
          <span>{figure(line.total)}</span>
        </button>
      </p>
      {/* role="list": without bullets, Safari's VoiceOver no longer calls a list one */}
      <ul id={id} className="balance-line-accounts" role="list" aria-label={`${line.label} accounts`} hidden={!open}>
        {line.accounts.map((account) => (
          <li key={account.key}>
            <span className="balance-line-name">
              {account.name}
              {account.hidden && <> <span className="balance-line-note">Hidden</span></>}
            </span>
            <span className="balance-line-amount">{figure(account.amount)}</span>
          </li>
        ))}
      </ul>
    </>
  );
};

export default BalanceLineRow;
