import React from "react";
import { accountTotals, balanceLines, noPriceWords, type LivePrice } from "../../utils/dashboard";
import { formatBtc, formatSignedUsd, formatUsd } from "../../utils/format";
import BalanceLineRow from "./BalanceLineRow";
import FigureRow from "./FigureRow";
import { useOpenLines } from "./useOpenLines";

interface PortfolioOverviewProps {
  balances: AccountBalance[];
  averageCostBasis: number | null;
  price: LivePrice;
}

/** What the BTC held would gain or lose if sold at today's price, from the
 * average cost per BTC. */
function unrealizedGains(price: LivePrice, averageCostBasis: number | null, totalBtc: number): React.ReactNode {
  // Without a price there is nothing to wait for: say why, as the price card does
  if (!price.loading && price.value === null) {
    return noPriceWords(price);
  }
  if (price.loading || price.value === null || averageCostBasis === null) {
    return "Loading...";
  }
  const gains = (price.value - averageCostBasis) * totalBtc;
  const isGain = gains >= 0;
  return (
    <span className={isGain ? "text-gain" : "text-loss"}>
      {formatSignedUsd(gains)}
    </span>
  );
}

/** Each kind's balance, with a caret listing its accounts where there's
 * something to list (#674: more than one, or a hidden one still holding
 * something), then the BTC held in all of them, what it cost on average and
 * what it would gain. */
const PortfolioOverview: React.FC<PortfolioOverviewProps> = ({ balances, averageCostBasis, price }) => {
  const [open, toggle] = useOpenLines();
  const totals = accountTotals(balances);
  return (
    <div className="card portfolio-overview">
      <h3 className="card-title">Portfolio Overview</h3>

      {balanceLines(balances).map((line) => (
        <BalanceLineRow key={line.key} line={line} open={open.includes(line.key)} onToggle={() => toggle(line.key)} />
      ))}

      <hr />

      <FigureRow label="Total BTC">{formatBtc(totals.totalBtc)}</FigureRow>
      <FigureRow label="Avg. Cost per BTC">
        {averageCostBasis !== null ? formatUsd(averageCostBasis) : "Loading..."}
      </FigureRow>
      <FigureRow label="Unrealized Gains/Losses">
        {unrealizedGains(price, averageCostBasis, totals.totalBtc)}
      </FigureRow>
    </div>
  );
};

export default PortfolioOverview;
