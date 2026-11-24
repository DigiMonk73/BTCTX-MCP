import React from "react";
import { acquiredText, type MovedCoin } from "../../utils/coinsMoved";
import { formatUsd, parseDecimal } from "../../utils/format";

/** A dollar figure a sale's piece may lack (a gift realizes none): blank. */
function usdOrBlank(value: string | null | undefined): string {
  return value == null ? "" : formatUsd(parseDecimal(value));
}

const TERM: Record<"LONG" | "SHORT", string> = { LONG: "Long-term", SHORT: "Short-term" };

/**
 * The coins a Transfer will move, or a Withdrawal or a Sell will dispose
 * of, in the order its save takes them, each with its date acquired,
 * amount and cost (#706, #711); a disposal's also with its proceeds, gain
 * and term, as Form 8949 will print them (#960). Read-only.
 */
const MovedCoinsTable: React.FC<{ coins: MovedCoin[]; caption: string }> = ({ coins, caption }) => {
  const disposed = coins.some((coin) => coin.term);
  const realized = coins.some((coin) => coin.proceeds_usd != null);
  return (
    <div className="table-scroll">
      <table className="table">
        <caption className="field-label">{caption}</caption>
        <thead>
          <tr>
            <th scope="col">Date acquired</th>
            <th scope="col" className="num">Amount (BTC)</th>
            <th scope="col" className="num">Cost (USD)</th>
            {realized && <th scope="col" className="num">Proceeds (USD)</th>}
            {realized && <th scope="col" className="num">Gain (USD)</th>}
            {disposed && <th scope="col">Term</th>}
          </tr>
        </thead>
        <tbody>
          {coins.map((coin, i) => (
            <tr key={i}>
              <td>{acquiredText(coin)}</td>
              <td className="num">{coin.btc}</td>
              <td className="num">{formatUsd(parseDecimal(coin.cost_usd))}</td>
              {realized && <td className="num">{usdOrBlank(coin.proceeds_usd)}</td>}
              {realized && <td className="num">{usdOrBlank(coin.gain_usd)}</td>}
              {disposed && <td>{coin.term ? TERM[coin.term] : ""}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default MovedCoinsTable;
