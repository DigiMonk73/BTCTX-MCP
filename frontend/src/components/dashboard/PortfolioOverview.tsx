import React from "react";
import { accountTotals, balanceLines, noPriceWords, unrealizedGain, type LivePrice } from "../../utils/dashboard";
import { formatBtc, formatSignedUsd, formatUsd } from "../../utils/format";
import BalanceLineRow from "./BalanceLineRow";
import FigureRow from "./FigureRow";
import { useOpenLines } from "./useOpenLines";

interface PortfolioOverviewProps {
  balances: AccountBalance[];
  averageCostBasis: number | null;
  price: LivePrice;
}

/** What the BTC held would gain or lose if sold at today's price: the
 * accounts' own gains added up (#770), never the rounded average's. */
function unrealizedGains(price: LivePrice, balances: AccountBalance[]): React.ReactNode {
  // Without a price there is nothing to wait for: say why, as the price card does
  if (!price.loading && price.value === null) {
    return noPriceWords(price);
  }
  const gains = price.loading ? null : unrealizedGain(price.value, balances);
  if (gains === null) {
    return "Loading...";
  }
  const isGain = gains >= 0;
  return (
    <span className={isGain ? "text-gain" : "text-loss"}>
      {formatSignedUsd(gains)}
    </span>
  );
}

/** Each kind's balance, with a caret listing its accounts where there's
 * something to list (#674: more than one, or a hidden one still holding
 * something; a bitcoin account's with its own cost and gain, #709), then
 * the BTC held in all of them, what it cost on average and what it would
 * gain. */
const PortfolioOverview: React.FC<PortfolioOverviewProps> = ({ balances, averageCostBasis, price }) => {
  const [open, toggle] = useOpenLines();
  const totals = accountTotals(balances);
  return (
    <div className="card portfolio-overview">
      <h3 className="card-title">Portfolio Overview</h3>

      {balanceLines(balances).map((line) => (
        <BalanceLineRow key={line.key} line={line} open={open.includes(line.key)} onToggle={() => toggle(line.key)}
          price={price.loading ? null : price.value} />
      ))}

      <hr />

      <FigureRow label="Total BTC">{formatBtc(totals.totalBtc)}</FigureRow>
      <FigureRow label="Avg. Cost per BTC">
        {averageCostBasis !== null ? formatUsd(averageCostBasis) : "Loading..."}
      </FigureRow>
      <FigureRow label="Unrealized Gains/Losses">
        {unrealizedGains(price, balances)}
      </FigureRow>
    </div>
  );
};

export default PortfolioOverview;
