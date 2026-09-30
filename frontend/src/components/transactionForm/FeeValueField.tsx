import React from "react";
import { useFormContext } from "react-hook-form";
import { formatUsd } from "../../utils/format";

/**
 * A BTC fee's USD value (transfers and BTC withdrawals), shown once there is
 * a fee: stored with the transaction; blank = fee x that day's price; a
 * typed value is kept.
 */
const FeeValueField: React.FC = () => {
  const { register, watch } = useFormContext<TransactionFormData>();
  const fee = watch("fee");
  if (!fee || Number.isNaN(fee) || fee <= 0) return null;
  const stored = watch("feeUSDStored");
  const manual = watch("feeUSDManual");
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
          ? `Stored: ${formatUsd(stored)} (fee × that day's BTC price). Type a value to replace it.`
          : "Leave blank to use fee × that day's BTC price, or type what the fee was worth."}
      </small>
    </div>
  );
};

export default FeeValueField;
