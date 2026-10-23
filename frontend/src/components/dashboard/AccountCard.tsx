import React, { useId } from "react";
import { toggleLabel, type CardRow, type KindCard } from "../../utils/dashboard";
import { formatBtc, formatUsd } from "../../utils/format";

/** A row's figures: a bank's dollars, a wallet's bitcoin, an exchange's dollars and bitcoin side by side. */
function rowFigures(card: KindCard, row: CardRow): string[] {
  if (card.kind === "bank") return [formatUsd(row.usd)];
  if (card.kind === "wallet") return [formatBtc(row.btc)];
  return [formatUsd(row.usd), formatBtc(row.btc)];
}

interface AccountCardProps {
  card: KindCard;
  open: boolean;
  onToggle: () => void;
}

/** One of the dashboard's three cards (P7's mockups, #356): a kind's total
 * and, when it has more than one account, a toggle that lists them. With
 * one account of a kind it looks as 1.x's balance did: no toggle. */
const AccountCard: React.FC<AccountCardProps> = ({ card, open, onToggle }) => {
  const id = useId();
  const label = toggleLabel(card, open);
  return (
    <section className="card account-card" aria-labelledby={`${id}-title`}>
      <h3 className="card-title" id={`${id}-title`}>{card.title}</h3>
      <div className="account-card-total">{card.kind === "wallet" ? formatBtc(card.btc) : formatUsd(card.usd)}</div>
      {card.kind === "exchange" && <div className="account-card-second">{formatBtc(card.btc)}</div>}
      {label && (
        <>
          <button
            type="button"
            className="btn btn-secondary btn-sm account-card-toggle"
            aria-expanded={open}
            aria-controls={`${id}-list`}
            onClick={onToggle}
          >
            {label}
          </button>
          <ul id={`${id}-list`} className="account-card-list" aria-label={`${card.title} accounts`} hidden={!open}>
            {card.rows.map((row) => (
              <li key={row.key}>
                <span className="account-card-name">
                  {row.name}
                  {row.hidden && <span className="account-card-note">Hidden</span>}
                </span>
                <span className="account-card-figures">
                  {rowFigures(card, row).map((figure) => <span key={figure}>{figure}</span>)}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
};

export default AccountCard;
