import React from "react";
import { howAcquired, type HeldLine } from "../../utils/chosenCoins";
import { acquiredText } from "../../utils/coinsMoved";
import { formatUsd, parseDecimal } from "../../utils/format";

const TERM: Record<HeldLine["term"], string> = { LONG: "Long-term", SHORT: "Short-term" };

interface Props {
  held: HeldLine[];
  lines: ChosenCoin[];
  wallet: string;
  onChange: (lines: ChosenCoin[]) => void;
}

/** Each field's name: its coins' date acquired, and the purchase's id
 * beside a date another line has too. */
function fieldLabels(held: HeldLine[]): string[] {
  const dates = held.map((line) => acquiredText(line));
  return held.map((line, i) => {
    const twice = dates.filter((d) => d === dates[i]).length > 1;
    return `BTC chosen from the coins acquired ${dates[i]}${twice ? `, transaction ${line.acquired_txn_id}` : ""}`;
  });
}

/**
 * What a wallet holds when the transaction comes, one purchase (or
 * deposit) a row: its coins' date acquired, under it their term then and
 * how and where they were acquired; their BTC, their cost under it; and the
 * BTC chosen from it (#711). Three columns, to fit the form's panel; the rows keep the
 * server's order, oldest first, as the save takes them; on a phone, each
 * row is a card (transactionForm.css).
 */
const ChosenCoinsTable: React.FC<Props> = ({ held, lines, wallet, onChange }) => {
  const labels = fieldLabels(held);
  const typed = (id: number | null) => lines.find((line) => line.acquired_txn_id === id)?.btc ?? "";
  // The lines in the table's order, then any the table doesn't list (a stored choice's)
  const update = (id: number, btc: string) => {
    const listed = new Set(held.map((line) => line.acquired_txn_id));
    const inTable = held.filter((line) => line.acquired_txn_id !== null).map((line) => ({
      acquired_txn_id: line.acquired_txn_id as number, btc: line.acquired_txn_id === id ? btc : typed(line.acquired_txn_id),
    }));
    onChange([...inTable, ...lines.filter((line) => !listed.has(line.acquired_txn_id))].filter((line) => line.btc !== ""));
  };
  return (
    <div className="table-scroll">
      <table className="table coins-picker-table">
        <caption className="field-label">Coins in {wallet} then</caption>
        <thead>
          <tr>
            <th scope="col">Acquired</th>
            <th scope="col" className="num">Held (BTC)</th>
            <th scope="col" className="num">Chosen (BTC)</th>
          </tr>
        </thead>
        <tbody>
          {held.map((line, i) => (
            <tr key={line.acquired_txn_id ?? `lot-${i}`}>
              <td data-label="Acquired">
                <span className="coins-picker-stack">
                  <span>{acquiredText(line)}</span>
                  <small className="field-hint"><span className="nowrap">{TERM[line.term]}</span> · {howAcquired(line)}</small>
                </span>
              </td>
              <td data-label="Held (BTC)" className="num">
                <span className="coins-picker-stack">
                  <span>{line.btc}</span>
                  <small className="field-hint nowrap">cost {formatUsd(parseDecimal(line.cost_usd))}</small>
                </span>
              </td>
              <td data-label="Chosen (BTC)" className="num">
                {line.acquired_txn_id !== null && (
                  <input type="text" inputMode="decimal" className="input" aria-label={labels[i]}
                    value={typed(line.acquired_txn_id)}
                    onChange={(e) => update(line.acquired_txn_id as number, e.target.value.trim())} />
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default ChosenCoinsTable;
