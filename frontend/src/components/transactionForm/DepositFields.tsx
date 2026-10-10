import React from "react";
import { useFormContext } from "react-hook-form";
import AccountAmountFields from "./AccountAmountFields";
import { takesOriginalDate } from "../../utils/transactionForm";

const INCOME_SOURCES = ["Income", "Interest", "Reward"];

/** A deposit; a BTC one also has its source and cost basis. */
const DepositFields: React.FC = () => {
  const { register, watch, formState: { errors } } = useFormContext<TransactionFormData>();
  const account = watch("account");
  const currency = watch("currency");
  const intoBtc = currency === "BTC" && (account === "Wallet" || account === "Exchange");
  const showSource = account === "Wallet" || (account === "Exchange" && currency === "BTC");
  // Income: basis = market value at receipt (the server fills a blank one)
  const source = watch("source");
  const isIncome = INCOME_SOURCES.includes(source ?? "");
  // Coins already owned, or a gift: their holding period runs from when they were first acquired
  const showOriginalDate = takesOriginalDate({ type: "Deposit", account, currency, source });

  return (
    <>
      <AccountAmountFields />

      {showSource && (
        <div className="field">
          <label htmlFor="tx-source">Source</label>
          <select
            id="tx-source"
            className="input"
            {...register("source", { required: true })}
          >
            <option value="N/A">N/A</option>
            <option value="MyBTC">MyBTC</option>
            <option value="Gift">Gift</option>
            <option value="Income">Income</option>
            <option value="Interest">Interest</option>
            <option value="Reward">Reward</option>
          </select>
        </div>
      )}

      {showOriginalDate && (
        <div className="field">
          <label htmlFor="tx-acquired-date">Date originally acquired</label>
          <input id="tx-acquired-date" type="date" className="input" {...register("acquiredDate")} />
          <small className="field-hint">
            Optional: when you first got these coins (for a gift, when the giver did). The holding period
            and Form 8949&apos;s date acquired count from it; blank uses this deposit&apos;s date.
          </small>
        </div>
      )}

      {intoBtc && (
        <div className="field">
          <label htmlFor="tx-cost-basis-usd">Cost Basis (USD)</label>
          <input
            id="tx-cost-basis-usd"
            type="number"
            step="0.01"
            className="input"
            aria-required={!isIncome}
            {...register("costBasisUSD", {
              valueAsNumber: true,
              // Not income: the basis must be stated (0 allowed); a blank one
              // would make the whole value gain when the BTC is sold.
              validate: (v) =>
                isIncome || (v !== undefined && !Number.isNaN(v)) ||
                "Enter this deposit's cost basis (type 0 if unknown).",
            })}
          />
          {errors.costBasisUSD && (
            <span className="field-error">{errors.costBasisUSD.message}</span>
          )}
          <small className="field-hint">
            {isIncome
              ? "Its USD value when you received it (also your income). Leave blank to use that day's BTC price."
              : "What this BTC cost you (type 0 if unknown). If you paid a miner fee in BTC externally, add its USD value."}
          </small>
        </div>
      )}
    </>
  );
};

export default DepositFields;
