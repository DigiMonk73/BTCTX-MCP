import React from "react";
import { useFormContext } from "react-hook-form";

/**
 * A Deposit's or Withdrawal's account, its currency (chosen only for the
 * Exchange; Bank is USD and Wallet BTC) and the amount.
 */
const AccountAmountFields: React.FC = () => {
  const { register, watch, formState: { errors } } = useFormContext<TransactionFormData>();
  const account = watch("account");
  return (
    <>
      <div className="field">
        <label htmlFor="tx-account">Account</label>
        <select
          id="tx-account"
          className="input"
          {...register("account", { required: true })}
        >
          <option value="">Select Account</option>
          <option value="Bank">Bank Account</option>
          <option value="Wallet">Bitcoin Wallet</option>
          <option value="Exchange">Exchange</option>
        </select>
        {errors.account && (
          <span className="field-error">Please select an account</span>
        )}
      </div>

      <div className="field">
        <label htmlFor="tx-currency">Currency</label>
        {account === "Exchange" ? (
          <select
            id="tx-currency"
            className="input"
            {...register("currency", { required: true })}
          >
            <option value="">Select Currency</option>
            <option value="USD">USD</option>
            <option value="BTC">BTC</option>
          </select>
        ) : (
          <input
            id="tx-currency"
            type="text"
            className="input"
            {...register("currency")}
            readOnly
          />
        )}
        {errors.currency && (
          <span className="field-error">Currency is required</span>
        )}
      </div>

      <div className="field">
        <label htmlFor="tx-amount">Amount</label>
        <input
          id="tx-amount"
          type="number"
          step="0.00000001"
          className="input"
          {...register("amount", {
            required: true,
            valueAsNumber: true,
          })}
        />
        {errors.amount && (
          <span className="field-error">Amount is required</span>
        )}
      </div>
    </>
  );
};

export default AccountAmountFields;
