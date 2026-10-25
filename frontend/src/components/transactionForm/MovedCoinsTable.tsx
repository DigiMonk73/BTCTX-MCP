import React from "react";
import { acquiredText, type MovedCoin } from "../../utils/coinsMoved";
import { formatUsd, parseDecimal } from "../../utils/format";

/**
 * The coins a Transfer will move, in the order its save takes them, each
 * with its date acquired, amount and cost (#706): a component of its own,
 * which choosing the coins (#711) builds on. `stale`: the list for the
 * transfer as it was a moment ago, shown dimmed while the new one is asked.
 */
const MovedCoinsTable: React.FC<{ coins: MovedCoin[]; stale: boolean }> = ({ coins, stale }) => (
  <div className="table-scroll" aria-busy={stale}>
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
        {coins.map((coin, i) => (
          <tr key={i}>
            <td>{acquiredText(coin)}</td>
            <td className="num">{coin.btc}</td>
            <td className="num">{formatUsd(parseDecimal(coin.cost_usd))}</td>
          </tr>
        ))}
      </tbody>
    </table>
  </div>
);

export default MovedCoinsTable;
