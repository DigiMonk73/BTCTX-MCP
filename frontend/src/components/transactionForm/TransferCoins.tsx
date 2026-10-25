import React from "react";
import { useFormContext, useWatch } from "react-hook-form";
import { chosenId } from "../../utils/accounts";
import { acquiredText, coinsPayload, feeLine, movesCoins, oldestFirstLine, type CoinsMoved } from "../../utils/coinsMoved";
import { formatUsd, parseDecimal } from "../../utils/format";
import { useCoinsMoved, type CoinsState } from "./useCoinsMoved";

/** The coins listed, each with its date acquired, amount and cost, and the fee's line. */
function coinsTable(answer: CoinsMoved): React.ReactNode {
  if (answer.coins === null) return <p className="field-hint">{answer.detail}</p>;
  if (answer.coins.length === 0) return null;
  const fee = feeLine(answer.fee_btc);
  return (
    <>
      <div className="table-scroll">
        <table className="table">
          <caption className="field-label">Coins that will move</caption>
          <thead>
            <tr>
              <th scope="col">Date acquired</th>
              <th scope="col" className="num">Amount (BTC)</th>
              <th scope="col" className="num">Cost (USD)</th>
            </tr>
          </thead>
          <tbody>
            {answer.coins.map((coin, i) => (
              <tr key={i}>
                <td>{acquiredText(coin)}</td>
                <td className="num">{coin.btc}</td>
                <td className="num">{formatUsd(parseDecimal(coin.cost_usd))}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {fee && <p className="field-hint">{fee}</p>}
    </>
  );
}

function shown(state: CoinsState): React.ReactNode {
  switch (state.kind) {
    case "asking":
      return <p className="field-hint">Working out which coins move…</p>;
    case "listed":
      return coinsTable(state.answer);
    case "refused":
      return (
        <p className="field-error">
          {state.reason ? `Which coins move can't be shown: ${state.reason}` : "Which coins move can't be shown right now."}
        </p>
      );
    default:
      return null;
  }
}

/**
 * Before a Transfer between two bitcoin accounts saves, the coins it will
 * move (#706; the owner's decision, 2026-10-25): the line saying the oldest
 * coins in the From account go first, and the list the server gives of the
 * coins its save takes, asked with the body the Save sends.
 */
const TransferCoins: React.FC<{ book: AccountBook; transactionId?: number | null }> = ({ book, transactionId }) => {
  const { control } = useFormContext<TransactionFormData>();
  const values = useWatch({ control }) as TransactionFormData;
  const state = useCoinsMoved(coinsPayload(values, book), transactionId);
  const fromId = chosenId(values.fromAccountId);
  if (!movesCoins(values, book) || fromId === undefined) return null;
  return (
    <div className="transfer-coins" aria-live="polite">
      <p className="field-hint">{oldestFirstLine(book, fromId)}</p>
      {shown(state)}
    </div>
  );
};

export default TransferCoins;
