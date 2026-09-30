import React from "react";
import { useFormContext } from "react-hook-form";
import FeeValueField from "./FeeValueField";

/**
 * A transfer between the user's accounts: the destination follows from the
 * source (useFieldAutofill), and a BTC transfer's fee is what was sent less
 * what arrived.
 */
const TransferFields: React.FC = () => {
  const { register, watch, formState: { errors } } = useFormContext<TransactionFormData>();
  const fromAccount = watch("fromAccount");
  const fromCurrency = watch("fromCurrency");
  return (
    <>
      <div className="field">
        <label htmlFor="tx-from-account">From Account</label>
        <select
          id="tx-from-account"
          className="input"
          {...register("fromAccount", { required: true })}
        >
          <option value="">Select From Account</option>
          <option value="Bank">Bank Account</option>
          <option value="Wallet">Bitcoin Wallet</option>
          <option value="Exchange">Exchange</option>
        </select>
        {errors.fromAccount && (
          <span className="field-error">From Account is required</span>
        )}
      </div>

      <div className="field">
        <label htmlFor="tx-from-currency">From Currency</label>
        {fromAccount === "Exchange" ? (
          <select
            id="tx-from-currency"
            className="input"
            {...register("fromCurrency", { required: true })}
          >
            <option value="">Select Currency</option>
            <option value="USD">USD</option>
            <option value="BTC">BTC</option>
          </select>
        ) : (
          <input
            id="tx-from-currency"
            type="text"
            className="input"
            {...register("fromCurrency")}
            readOnly
          />
        )}
        {errors.fromCurrency && (
          <span className="field-error">From Currency is required</span>
        )}
      </div>

      <div className="field">
        <label htmlFor="tx-amount-from">Amount (From)</label>
        <input
          id="tx-amount-from"
          type="number"
          step="0.00000001"
          className="input"
          {...register("amountFrom", {
            required: true,
            valueAsNumber: true,
          })}
        />
        {errors.amountFrom && (
          <span className="field-error">Amount (From) is required</span>
        )}
      </div>

      <div className="field">
        <label htmlFor="tx-to-account">To Account</label>
        <input
          id="tx-to-account"
          type="text"
          className="input"
          {...register("toAccount")}
          readOnly
        />
      </div>

      <div className="field">
        <label htmlFor="tx-to-currency">To Currency</label>
        <input
          id="tx-to-currency"
          type="text"
          className="input"
          {...register("toCurrency")}
          readOnly
        />
      </div>

      <div className="field">
        <label htmlFor="tx-amount-to">Amount (To)</label>
        <input
          id="tx-amount-to"
          type="number"
          step="0.00000001"
          className="input"
          {...register("amountTo", {
            required: true,
            valueAsNumber: true,
          })}
        />
        {errors.amountTo && (
          <span className="field-error">Amount (To) is required</span>
        )}
      </div>

      {fromCurrency === "BTC" ? (
        <>
          <div className="field">
            <label htmlFor="tx-fee-btc">Fee (BTC)</label>
            <input
              id="tx-fee-btc"
              type="number"
              step="0.00000001"
              className="input"
              {...register("fee", { valueAsNumber: true })}
              readOnly
            />
          </div>
          <FeeValueField />
        </>
      ) : (
        <div className="field">
          <label htmlFor="tx-fee-usd">Fee (USD)</label>
          <input
            id="tx-fee-usd"
            type="number"
            step="0.01"
            className="input"
            defaultValue={0}
            {...register("fee", { valueAsNumber: true })}
          />
        </div>
      )}
    </>
  );
};

export default TransferFields;
