import React from "react";
import { noPriceWords, type AccountTotals, type LivePrice } from "../../utils/dashboard";
import { formatBtc, formatSignedUsd, formatUsd } from "../../utils/format";
import FigureRow from "./FigureRow";

interface PortfolioOverviewProps {
  totals: AccountTotals;
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

/** The BTC held in all your accounts, what it cost on average and what it
 * would gain; each kind's balances are on the cards above (AccountCards). */
const PortfolioOverview: React.FC<PortfolioOverviewProps> = ({ totals, averageCostBasis, price }) => (
  <div className="card portfolio-overview">
    <h3 className="card-title">Portfolio Overview</h3>

    <FigureRow label="Total BTC">{formatBtc(totals.totalBtc)}</FigureRow>
    <FigureRow label="Avg. Cost per BTC">
      {averageCostBasis !== null ? formatUsd(averageCostBasis) : "Loading..."}
    </FigureRow>
    <FigureRow label="Unrealized Gains/Losses">
      {unrealizedGains(price, averageCostBasis, totals.totalBtc)}
    </FigureRow>
  </div>
);

export default PortfolioOverview;
