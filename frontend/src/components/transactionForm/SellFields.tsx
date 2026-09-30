import React from "react";
import { useFormContext } from "react-hook-form";
import BrokerReportingField from "./BrokerReportingField";

/** A Sell on the exchange: the BTC sold, its gross proceeds and the fee. */
const SellFields: React.FC = () => {
  const { register, formState: { errors } } = useFormContext<TransactionFormData>();
  return (
    <>
      <div className="field">
        <label htmlFor="tx-account">Account</label>
        <input
          id="tx-account"
          type="text"
          className="input"
          value="Exchange"
          {...register("account")}
          readOnly
        />
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
        <label htmlFor="tx-gross-proceeds-usd">Gross Proceeds (USD)</label>
        <input
          id="tx-gross-proceeds-usd"
          type="number"
          step="0.01"
          className="input"
          {...register("grossProceedsUSD", {
            required: true,
            valueAsNumber: true,
          })}
        />
        {errors.grossProceedsUSD && (
          <span className="field-error">Gross proceeds is required</span>
        )}
        <small className="field-hint">
          The backend will subtract fees to calculate net proceeds.
        </small>
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

      <BrokerReportingField />
    </>
  );
};

export default SellFields;
