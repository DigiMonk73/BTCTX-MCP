import React from "react";
import type { AccountTotals, LivePrice } from "../../utils/dashboard";
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
    return price.off ? "Prices off" : "No price";
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

const PortfolioOverview: React.FC<PortfolioOverviewProps> = ({ totals, averageCostBasis, price }) => (
  <div className="card portfolio-overview">
    <h3 className="card-title">Portfolio Overview</h3>

    <FigureRow label="Bank (USD)">{formatUsd(totals.bank)}</FigureRow>
    <FigureRow label="Exchange (USD)">{formatUsd(totals.exchangeUsd)}</FigureRow>
    <FigureRow label="Exchange (BTC)">{formatBtc(totals.exchangeBtc)}</FigureRow>
    <FigureRow label="Wallet (BTC)">{formatBtc(totals.wallet)}</FigureRow>

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

export default PortfolioOverview;
