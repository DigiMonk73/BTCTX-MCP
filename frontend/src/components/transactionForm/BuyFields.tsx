import React from "react";
import { useFormContext } from "react-hook-form";

/** A Buy: USD from Exchange USD (or the bank, for an auto-buy) into BTC. */
const BuyFields: React.FC = () => {
  const { register, formState: { errors } } = useFormContext<TransactionFormData>();
  return (
    <>
      <div className="field">
        <label htmlFor="tx-from-account">From Account</label>
        <select
          id="tx-from-account"
          className="input"
          {...register("buyFromAccount", { required: true })}
        >
          <option value="Exchange">Exchange USD</option>
          <option value="Bank">Bank (auto-buy)</option>
        </select>
        <small className="field-hint">
          Select where the USD is coming from.
        </small>
      </div>

      <div className="field">
        <label htmlFor="tx-amount-usd">Amount USD</label>
        <input
          id="tx-amount-usd"
          type="number"
          step="0.01"
          className="input"
          {...register("amountUSD", {
            required: true,
            valueAsNumber: true,
          })}
        />
        {errors.amountUSD && (
          <span className="field-error">Amount USD is required</span>
        )}
      </div>

      <div className="field">
        <label htmlFor="tx-amount-btc">Amount BTC</label>
        <input
          id="tx-amount-btc"
          type="number"
          step="0.00000001"
          className="input"
          {...register("amountBTC", {
            required: true,
            valueAsNumber: true,
          })}
        />
        {errors.amountBTC && (
          <span className="field-error">Amount BTC is required</span>
        )}
      </div>

      <div className="field">
        <label htmlFor="tx-fee-usd">Fee (USD)</label>
        <input
          id="tx-fee-usd"
          type="number"
          step="0.00000001"
          className="input"
          {...register("fee", { valueAsNumber: true })}
        />
      </div>
    </>
  );
};

export default BuyFields;
