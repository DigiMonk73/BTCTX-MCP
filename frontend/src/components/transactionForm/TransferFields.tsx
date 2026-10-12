import React from "react";
import { useFormContext } from "react-hook-form";
import { ONE_WALLET_HINT } from "../../utils/disclaimer";
import { transferDestinations } from "../../utils/transactionForm";
import FeeValueField from "./FeeValueField";

// A BTC account sent to itself (#159): how the choice reads, and what it records
const WITHIN_LABEL: Partial<Record<AccountType, string>> = {
  Wallet: "Wallet: consolidate / move within the same wallet",
  Exchange: "Exchange: move between exchanges BitcoinTX counts as one",
};
const WITHIN_HINT =
  "Only the network fee is recorded: it's a disposal of your oldest coins at the fee's value (Form 8949, " +
  "box I or L). Your coins, their dates and cost basis stay as they are.";

/**
 * A transfer between the user's accounts: the destination follows from the
 * source (useFieldAutofill; a BTC one can also be the same account, a
 * consolidation), and a BTC transfer's fee is what was sent less what arrived.
 */
const TransferFields: React.FC = () => {
  const { register, watch, setValue, getValues, formState: { errors } } = useFormContext<TransactionFormData>();
  const fromAccount = watch("fromAccount");
  const fromCurrency = watch("fromCurrency");
  const toAccount = watch("toAccount");
  const destinations = transferDestinations(fromAccount, fromCurrency);
  const within = fromCurrency === "BTC" && !!fromAccount && toAccount === fromAccount;
  // Another source: its usual destination, not the old one. Set here, not left
  // to useFieldAutofill: a destination select that mounts without a value
  // takes its first option in the form's values without a re-render, and
  // the form would show a destination it didn't know about
  const newSource = {
    onChange: () => {
      const { fromAccount: account, fromCurrency: currency } = getValues();
      setValue("toAccount", transferDestinations(account, currency)[0]);
    },
  };
  return (
    <>
      <div className="field">
        <label htmlFor="tx-from-account">From Account</label>
        <select
          id="tx-from-account"
          className="input"
          {...register("fromAccount", { required: true, ...newSource })}
        >
          <option value="">Select From Account</option>
          <option value="Bank">Bank Account</option>
          <option value="Wallet">Bitcoin Wallet</option>
          <option value="Exchange">Exchange</option>
        </select>
        {errors.fromAccount && (
          <span className="field-error">From Account is required</span>
        )}
        {fromAccount === "Wallet" && <small className="field-hint">{ONE_WALLET_HINT}</small>}
      </div>

      <div className="field">
        <label htmlFor="tx-from-currency">From Currency</label>
        {fromAccount === "Exchange" ? (
          <select
            id="tx-from-currency"
            className="input"
            {...register("fromCurrency", { required: true, ...newSource })}
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
        {destinations.length > 1 ? (
          <select id="tx-to-account" className="input" {...register("toAccount")}>
            {destinations.map((account) => (
              <option key={account} value={account}>
                {account === fromAccount ? WITHIN_LABEL[account] : account}
              </option>
            ))}
          </select>
        ) : (
          <input
            id="tx-to-account"
            type="text"
            className="input"
            {...register("toAccount")}
            readOnly
          />
        )}
        {within && <small className="field-hint">{WITHIN_HINT}</small>}
        {!within && toAccount === "Wallet" && <small className="field-hint">{ONE_WALLET_HINT}</small>}
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
            required: "Amount (To) is required",
            valueAsNumber: true,
            // Within one account only the fee is recorded, so there must be one
            validate: (v, values) =>
              !(values.fromCurrency === "BTC" && values.toAccount === values.fromAccount) ||
              (v ?? 0) < (values.amountFrom ?? 0) ||
              "A move within the same account records only its network fee: Amount (To) must be less than Amount (From).",
          })}
        />
        {errors.amountTo && (
          <span className="field-error">{errors.amountTo.message || "Amount (To) is required"}</span>
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
