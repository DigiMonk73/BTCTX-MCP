import React from "react";
import type { LivePrice } from "../../utils/dashboard";
import { formatBtc, formatUsd } from "../../utils/format";
import FigureRow from "./FigureRow";

interface IncomeFeesCardProps {
  gains: GainsAndLosses;
  price: LivePrice;
}

/** Income by source (USD and BTC), gifts received, and the fees paid, with
 * the BTC fees valued at today's price. */
const IncomeFeesCard: React.FC<IncomeFeesCardProps> = ({ gains, price }) => (
  <div className="card income-fees-container">
    <h3 className="card-title">Income & Fees</h3>

    <FigureRow label="Income (earned)">
      {formatUsd(gains.income_earned)} (
      <em>{formatBtc(gains.income_btc)}</em>)
    </FigureRow>
    <FigureRow label="Interest (earned)">
      {formatUsd(gains.interest_earned)} (
      <em>{formatBtc(gains.interest_btc)}</em>)
    </FigureRow>
    <FigureRow label="Rewards (earned)">
      {formatUsd(gains.rewards_earned)} (
      <em>{formatBtc(gains.rewards_btc)}</em>)
    </FigureRow>

    <hr />

    <FigureRow label="Total Income">{formatUsd(gains.total_income)}</FigureRow>

    <FigureRow label="Gifts (received)">
      {formatUsd(gains.gifts_received)} (
      <em>{formatBtc(gains.gifts_btc)}</em>)
    </FigureRow>
    <p className="gifts-note">
      <em>(not added to income or gains)</em>
    </p>

    <hr />

    <h4 className="card-subtitle">Fees</h4>
    <FigureRow label="Fees (USD)">{formatUsd(gains.fees.USD)}</FigureRow>
    <FigureRow label="Fees (BTC)">{formatBtc(gains.fees.BTC)}</FigureRow>

    {price.loading ? (
      <FigureRow label="Total Fees in USD (approx)">Loading...</FigureRow>
    ) : price.value !== null ? (
      <FigureRow label="Total Fees in USD (approx)">
        {formatUsd(gains.fees.USD + gains.fees.BTC * price.value)}
      </FigureRow>
    ) : (
      <FigureRow label="Total Fees in USD">N/A</FigureRow>
    )}
  </div>
);

export default IncomeFeesCard;
