import React from "react";
import { useFormContext } from "react-hook-form";
import { formatUsd } from "../../utils/format";
import { priceUsedWords } from "../../utils/priceUsed";
import { useBlankPriceSource } from "./useBlankPriceSource";

/**
 * A BTC fee's USD value (transfers and BTC withdrawals), shown once there is
 * a fee: stored with the transaction; blank = fee x the price when its hour
 * began; a typed value is kept. A stored value says which price it came from.
 */
const FeeValueField: React.FC = () => {
  const { register, watch } = useFormContext<TransactionFormData>();
  const priced = useBlankPriceSource().hour; // before the early return: hooks run every render
  const fee = watch("fee");
  if (!fee || Number.isNaN(fee) || fee <= 0) return null;
  const stored = watch("feeUSDStored");
  const manual = watch("feeUSDManual");
  const moment = watch("priceMoment") === "day" ? "that day's 00:00 UTC" : "that hour's";
  const used = watch("priceUsed");
  return (
    <div className="field">
      <label htmlFor="tx-fee-value-usd">Fee value (USD)</label>
      <input
        id="tx-fee-value-usd"
        type="number"
        step="0.01"
        min="0"
        className="input"
        {...register("feeUSD", { valueAsNumber: true })}
      />
      <small className="field-hint">
        {stored != null && !manual
          ? `Stored: ${formatUsd(stored)} (fee × ${used ? priceUsedWords(used) : `${moment} BTC price`}). Type a value to replace it.`
          : "Leave blank to use fee × the BTC price when that hour began (that day's, where there's no "
            + `hourly price), or type what the fee was worth. ${priced}`.trim()}
      </small>
    </div>
  );
};

export default FeeValueField;
