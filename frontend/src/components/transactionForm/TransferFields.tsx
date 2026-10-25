import React from "react";
import { useFormContext } from "react-hook-form";
import {
  accountCurrency, accountKind, accountName, chosenId, exchangeName, isBtcAccount, transferTargets, visibleAccounts,
} from "../../utils/accounts";
import { WALLET_HINT } from "../../utils/disclaimer";
import { transferAmountProblem } from "../../utils/transferAmounts";
import AccountPicker from "./AccountPicker";
import FeeValueField from "./FeeValueField";
import TransferCoins from "./TransferCoins";

// A BTC account sent to itself (#159): how the choice reads, and what it records.
// It moves no coins, so it never says "move" (#705)
const WITHIN_LABEL: Partial<Record<AccountKind, (book: AccountBook, id: number) => string>> = {
  wallet: (book, id) => `${accountName(book, id)}: consolidate within the same wallet`,
  exchange: (book, id) => `${exchangeName(book, id)}: consolidate within the same exchange`,
};
const WITHIN_HINT =
  "Only the network fee is recorded: it's a disposal of your oldest coins at the fee's value (Form 8949, " +
  "box I or L; C or F before 2025). Your coins, their dates and cost basis stay as they are.";
// A move to another wallet or exchange is a Transfer into that account, never
// a consolidation: each keeps its own lots (2.0 spec 5.5)
const MOVE_ELSEWHERE_HINT: Partial<Record<AccountKind, string>> = {
  wallet:
    "Moving coins to another of your wallets? Choose that wallet as To Account, after adding it in " +
    "Settings → Wallets, exchanges and banks if it isn't listed.",
  exchange:
    "Moving coins to another exchange? Choose that exchange's BTC account as To Account, after adding the " +
    "exchange in Settings → Wallets, exchanges and banks if it isn't listed.",
};

/** The destination: an account of the From's currency, or the From itself
 * for a bitcoin account (#159); filled only when exactly one fits (5.13). */
const ToAccountField: React.FC<{ book: AccountBook; fromId: number | undefined }> = ({ book, fromId }) => {
  const { watch } = useFormContext<TransactionFormData>();
  const toId = chosenId(watch("toAccountId"));
  const within = toId !== undefined && toId === fromId && isBtcAccount(book, fromId);
  const kind = accountKind(book, fromId);
  return (
    <AccountPicker
      id="tx-to-account"
      label="To Account"
      field="toAccountId"
      book={book}
      choices={(saved) => transferTargets(book, fromId, saved)}
      placeholder="Select To Account"
      requiredMessage="To Account is required"
      optionLabel={(id) => (id === fromId && kind ? WITHIN_LABEL[kind]?.(book, id) : undefined) ?? accountName(book, id)}
      fillable={(id) => id !== fromId} // a consolidation records only a fee: chosen, never filled in
      deps={["amountTo"]}
    >
      {within && <small className="field-hint">{WITHIN_HINT}</small>}
      {within && kind && MOVE_ELSEWHERE_HINT[kind] && <small className="field-hint">{MOVE_ELSEWHERE_HINT[kind]}</small>}
      {!within && accountKind(book, toId) === "wallet" && <small className="field-hint">{WALLET_HINT}</small>}
    </AccountPicker>
  );
};

/**
 * A transfer between the user's accounts: the destination within the
 * source's currency (a bitcoin one can also be the same account, a
 * consolidation), and the fee is what was sent less what arrived, in
 * bitcoin or in dollars (#447; useFieldAutofill). Between two bitcoin
 * accounts, the coins that will move, before it saves (#706).
 */
const TransferFields: React.FC<{ book: AccountBook; transactionId?: number | null }> = ({ book, transactionId }) => {
  const { register, watch, getValues, setValue, formState: { errors } } = useFormContext<TransactionFormData>();
  const fromId = chosenId(watch("fromAccountId"));
  // A new From never changes what the To chosen means, so the To goes, as 1.x
  // set the new From's own, when it would be the new From: a consolidation,
  // which records only a fee (#159); and when it was the old From (`fromId`,
  // the From this render showed): that consolidation would move coins into
  // the old From's lots (#719).
  const toKeepsItsMeaning = () => {
    const from = chosenId(getValues("fromAccountId"));
    const to = chosenId(getValues("toAccountId"));
    if (from !== fromId && to !== undefined && (to === from || to === fromId)) {
      setValue("toAccountId", undefined);
    }
  };
  const fromCurrency = accountCurrency(book, fromId);
  const amountProblem = (field: "amountFrom" | "amountTo") =>
    (_v: unknown, values: TransactionFormData) => transferAmountProblem(values, book, field) ?? true;
  return (
    <>
      <AccountPicker
        id="tx-from-account"
        label="From Account"
        field="fromAccountId"
        book={book}
        choices={(saved) => visibleAccounts(book, saved)}
        placeholder="Select From Account"
        requiredMessage="From Account is required"
        deps={["amountFrom", "amountTo"]} // messages about the old source go
        onChange={toKeepsItsMeaning}
      >
        {accountKind(book, fromId) === "wallet" && <small className="field-hint">{WALLET_HINT}</small>}
      </AccountPicker>

      <div className="field">
        <label htmlFor="tx-from-currency">From Currency</label>
        <input id="tx-from-currency" type="text" className="input" value={fromCurrency ?? ""} readOnly />
      </div>

      <div className="field">
        <label htmlFor="tx-amount-from">Amount (From)</label>
        <input
          id="tx-amount-from"
          type="number"
          step="0.00000001"
          className="input"
          {...register("amountFrom", {
            required: "Amount (From) is required",
            valueAsNumber: true,
            deps: "amountTo",
            validate: amountProblem("amountFrom"),
          })}
        />
        {errors.amountFrom && (
          <span className="field-error">{errors.amountFrom.message || "Amount (From) is required"}</span>
        )}
      </div>

      <ToAccountField book={book} fromId={fromId} />

      {/* A transfer stays in one currency (5.5): the To's is the From's */}
      <div className="field">
        <label htmlFor="tx-to-currency">To Currency</label>
        <input id="tx-to-currency" type="text" className="input" value={fromCurrency ?? ""} readOnly />
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
            validate: amountProblem("amountTo"),
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
            readOnly
          />
          <small className="field-hint">Amount (From) less Amount (To): what the transfer cost.</small>
        </div>
      )}

      <TransferCoins book={book} transactionId={transactionId} />
    </>
  );
};

export default TransferFields;
