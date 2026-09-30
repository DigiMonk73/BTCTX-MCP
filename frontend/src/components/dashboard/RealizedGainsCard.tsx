import React from "react";
import { gainClass } from "../../utils/dashboard";
import { formatSignedUsd, formatUsd } from "../../utils/format";
import FigureRow from "./FigureRow";

/** Realized gains and losses (FIFO), short and long term, all time and this
 * year. */
const RealizedGainsCard: React.FC<{ gains: GainsAndLosses }> = ({ gains }) => (
  <div className="card realized-gains-container">
    <h3 className="card-title">Realized Gains/Losses (FIFO)</h3>

    <FigureRow label="Short-Term Gains" className={gains.short_term_gains > 0 ? "text-gain" : ""}>
      {formatSignedUsd(gains.short_term_gains)}
    </FigureRow>
    <FigureRow label="Short-Term Losses" className={gains.short_term_losses > 0 ? "text-loss" : ""}>
      {formatUsd(-gains.short_term_losses)}
    </FigureRow>
    <FigureRow label="Net Short-Term" className={gainClass(gains.short_term_net)}>
      {formatSignedUsd(gains.short_term_net)}
    </FigureRow>

    <hr />

    <FigureRow label="Long-Term Gains" className={gains.long_term_gains > 0 ? "text-gain" : ""}>
      {formatSignedUsd(gains.long_term_gains)}
    </FigureRow>
    <FigureRow label="Long-Term Losses" className={gains.long_term_losses > 0 ? "text-loss" : ""}>
      {formatUsd(-gains.long_term_losses)}
    </FigureRow>
    <FigureRow label="Net Long-Term" className={gainClass(gains.long_term_net)}>
      {formatSignedUsd(gains.long_term_net)}
    </FigureRow>

    <hr />

    <FigureRow label="Total Net Capital Gains" className={gainClass(gains.total_net_capital_gains)}>
      {formatSignedUsd(gains.total_net_capital_gains)}
    </FigureRow>
    <FigureRow label="Year to Date Gains" className={gainClass(gains.year_to_date_capital_gains)}>
      {formatSignedUsd(gains.year_to_date_capital_gains)}
    </FigureRow>
  </div>
);

export default RealizedGainsCard;
