import React from "react";
import { useFormContext } from "react-hook-form";
import AccountAmountFields from "./AccountAmountFields";
import { takesOriginalDate } from "../../utils/transactionForm";

// Valued when acquired: the server fills a blank basis from that day's price
// (an inheritance's: the date of death)
const VALUED_SOURCES = ["Income", "Interest", "Reward", "Rebate", "Inherited"];
// What tells Reward (income) and Rebate (not income, #98) apart, and the
// rules of an inheritance (#154)
const SOURCE_HINTS: Record<string, string> = {
  Reward: "Mining, staking, or a sign-up or referral bonus: income.",
  Rebate: "Bitcoin back for spending, such as a rewards card's sats-back: not income; its value is its cost basis.",
  Inherited:
    "Bitcoin you inherited from someone who died. Its cost basis is its value on the date of death, any sale " +
    "of it is long-term however soon you sell, and Form 8949 says INHERITED instead of a date acquired " +
    "(IRC §1014, §1223(9)).",
};

/** What the Cost Basis field asks for: a gift's basis is the giver's (#115). */
function basisHint(source: string | undefined, valued: boolean): string {
  if (source === "Inherited") {
    return "Its USD value on the date of death, or on the estate's alternate valuation date if it chose one. " +
      "If the estate's Form 8971, Schedule A, gives a value marked as having increased the estate tax, your " +
      "basis can't be more. Leave blank to use the date of death's BTC price.";
  }
  if (source === "Rebate") {
    return "Its USD value when you received it (its cost basis, not income). Leave blank to use that day's BTC price.";
  }
  if (valued) {
    return "Its USD value when you received it (also your income). Leave blank to use that day's BTC price.";
  }
  if (source === "Gift") {
    return "The giver's cost basis: what they paid for these coins (type 0 if unknown).";
  }
  return "What this BTC cost you (type 0 if unknown). If you paid a miner fee in BTC externally, add its USD value.";
}

/** A My BTC or Gift deposit's optional "Date originally acquired", or an
 * inheritance's required "Date of death" (#154): the same field. */
const OriginalDateField: React.FC<{ inherited: boolean }> = ({ inherited }) => {
  const { register, formState: { errors } } = useFormContext<TransactionFormData>();
  if (!inherited) {
    return (
      <div className="field">
        <label htmlFor="tx-acquired-date">Date originally acquired</label>
        <input id="tx-acquired-date" type="date" className="input" {...register("acquiredDate")} />
        <small className="field-hint">
          Optional: when you first got these coins (for a gift, when the giver did). The holding period
          and Form 8949&apos;s date acquired count from it; blank uses this deposit&apos;s date.
        </small>
      </div>
    );
  }
  return (
    <div className="field">
      <label htmlFor="tx-acquired-date">Date of death</label>
      <input
        id="tx-acquired-date"
        type="date"
        className="input"
        aria-required
        {...register("acquiredDate", {
          validate: (v, values) => values.source !== "Inherited" || !!v || "Enter the date of death.",
        })}
      />
      {errors.acquiredDate && <span className="field-error">{errors.acquiredDate.message}</span>}
      <small className="field-hint">
        The day the person died. The cost basis is the value that day, and these coins take their place in
        first in, first out from that date.
      </small>
    </div>
  );
};

/** A deposit; a BTC one also has its source and cost basis. */
const DepositFields: React.FC = () => {
  const { register, watch, formState: { errors } } = useFormContext<TransactionFormData>();
  const account = watch("account");
  const currency = watch("currency");
  const intoBtc = currency === "BTC" && (account === "Wallet" || account === "Exchange");
  const showSource = account === "Wallet" || (account === "Exchange" && currency === "BTC");
  // Income, rebates, inheritances: basis = value when acquired (the server fills a blank one)
  const source = watch("source");
  const isValued = VALUED_SOURCES.includes(source ?? "");
  // Coins already owned, a gift or an inheritance: dated from when they were first acquired (or the death)
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
            <option value="Inherited">Inherited</option>
            <option value="Income">Income</option>
            <option value="Interest">Interest</option>
            <option value="Reward">Reward</option>
            <option value="Rebate">Rebate</option>
          </select>
          {source && SOURCE_HINTS[source] && <small className="field-hint">{SOURCE_HINTS[source]}</small>}
        </div>
      )}

      {showOriginalDate && <OriginalDateField inherited={source === "Inherited"} />}

      {intoBtc && (
        <div className="field">
          <label htmlFor="tx-cost-basis-usd">Cost Basis (USD)</label>
          <input
            id="tx-cost-basis-usd"
            type="number"
            step="0.01"
            className="input"
            aria-required={!isValued}
            {...register("costBasisUSD", {
              valueAsNumber: true,
              // Not income or a rebate: the basis must be stated (0 allowed); a
              // blank one would make the whole value gain when the BTC is sold.
              validate: (v) =>
                isValued || (v !== undefined && !Number.isNaN(v)) ||
                "Enter this deposit's cost basis (type 0 if unknown).",
            })}
          />
          {errors.costBasisUSD && (
            <span className="field-error">{errors.costBasisUSD.message}</span>
          )}
          <small className="field-hint">{basisHint(source, isValued)}</small>
        </div>
      )}
    </>
  );
};

export default DepositFields;
