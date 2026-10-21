import React from "react";
import ValueOrigin from "./ValueOrigin";
import { useFormContext } from "react-hook-form";
import AccountAmountFields from "./AccountAmountFields";
import { isBtcAccount } from "../../utils/accounts";
import { takesOriginalDate } from "../../utils/transactionForm";
import { useBlankPriceSource, type BlankPriceWords } from "./useBlankPriceSource";

// Valued when acquired: the server fills a blank basis from that hour's price
// (an inheritance's: the date of death's day price, #173)
const VALUED_SOURCES = ["Income", "Interest", "Reward", "Rebate", "Inherited"];
// Where there's no hourly price (before 2013, or an own mempool server
// without the public fallback, for hours before its record), the day's
const BLANK_IS_PRICED =
  "Leave blank to use the BTC price when that hour began (that day's, where there's no hourly price).";
// What tells Reward (income) and Rebate (not income, #98) apart, and the
// rules of an inheritance (#154). Sats-back on cash equivalents is income
// (Anikeev v. Commissioner, T.C. Memo. 2021-23: rewards on money orders), #160
const SOURCE_HINTS: Record<string, string> = {
  Reward: "Mining, staking, or a sign-up or referral bonus: income.",
  Rebate:
    "Bitcoin back for spending, such as a rewards card's sats-back: not income; its value is its cost basis. " +
    "Sats-back for buying money orders or other cash equivalents is income: use Reward.",
  Inherited:
    "Bitcoin you inherited from someone who died. Its cost basis is its value on the date of death, any sale " +
    "of it is long-term however soon you sell, and Form 8949 says INHERITED instead of a date acquired " +
    "(IRC §1014, §1223(9)).",
};

/** What the Cost Basis field asks for: a gift's basis is the giver's (#115); a blank
 * value's price says where it comes from (`priced`, #208). */
function basisHint(source: string | undefined, valued: boolean, priced: BlankPriceWords): string {
  if (source === "Inherited") {
    return ("Its USD value on the date of death, or on the estate's alternate valuation date if it chose one. " +
      "If the estate's Form 8971, Schedule A, gives a value marked as having increased the estate tax, your " +
      `basis can't be more. Leave blank to use the date of death's BTC price. ${priced.day}`).trim();
  }
  if (source === "Rebate") {
    return `Its USD value when you received it (its cost basis, not income). ${BLANK_IS_PRICED} ${priced.hour}`.trim();
  }
  if (valued) {
    return `Its USD value when you received it (also your income). ${BLANK_IS_PRICED} ${priced.hour}`.trim();
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

/** A deposit; one into a bitcoin account also has its source and cost basis. */
const DepositFields: React.FC<{ book: AccountBook }> = ({ book }) => {
  const { register, watch, setValue, formState: { errors } } = useFormContext<TransactionFormData>();
  const priced = useBlankPriceSource();
  // A blank select is "" until setValueAs runs, and "" is not an id (5.13).
  const watched = watch("toAccountId");
  const toAccountId = typeof watched === "number" ? watched : undefined;
  // Income is valued at receipt only in a bitcoin account (AGENTS.md "Income deposits").
  const btc = isBtcAccount(book, toAccountId);
  // Income, rebates, inheritances: basis = value when acquired (the server fills a blank one)
  const source = watch("source");
  const isValued = VALUED_SOURCES.includes(source ?? "");
  // Coins already owned, a gift or an inheritance: dated from when they were first acquired (or the death)
  const showOriginalDate = takesOriginalDate({ type: "Deposit", toAccountId, source }, book);
  const inherited = source === "Inherited";
  // A date of death isn't a date originally acquired, nor a value at death a
  // giver's cost (#154): switching to or from Inherited asks for both again
  // (`source` is still the one before the change)
  const clearIfInheritance = (next: string) => {
    if (inherited !== (next === "Inherited")) {
      setValue("acquiredDate", "");
      setValue("costBasisUSD", undefined);
    }
  };

  return (
    <>
      <AccountAmountFields book={book} field="toAccountId" />

      {btc && (
        <div className="field">
          <label htmlFor="tx-source">Source</label>
          <select
            id="tx-source"
            className="input"
            {...register("source", { required: true, onChange: (e) => clearIfInheritance(e.target.value) })}
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

      {/* A new input each time the clearing above runs: WebKit on macOS keeps
          judging a date input invalid once a script clears it, which blocks
          Save without a word (#456) */}
      {showOriginalDate && <OriginalDateField key={inherited ? "death" : "acquired"} inherited={inherited} />}

      {btc && (
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
          <small className="field-hint">{basisHint(source, isValued, priced)}</small>
          {isValued && <ValueOrigin fromPrice="costBasisFromPrice" stored="costBasisStored" shown="costBasisUSD" />}
        </div>
      )}
    </>
  );
};

export default DepositFields;
