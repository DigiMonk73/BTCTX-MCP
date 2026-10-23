import React from "react";
import { useFormContext } from "react-hook-form";
import {
  accountCurrency, accountKind, accountName, chosenId, exchangeName, isBtcAccount, transferTargets, visibleAccounts,
} from "../../utils/accounts";
import { ONE_WALLET_HINT } from "../../utils/disclaimer";
import { transferAmountProblem } from "../../utils/transferAmounts";
import AccountPicker from "./AccountPicker";
import FeeValueField from "./FeeValueField";

// A BTC account sent to itself (#159): how the choice reads, and what it records
const WITHIN_LABEL: Partial<Record<AccountKind, (book: AccountBook, id: number) => string>> = {
  wallet: (book, id) => `${accountName(book, id)}: consolidate / move within the same wallet`,
  exchange: (book, id) => `${exchangeName(book, id)}: move between exchanges BitcoinTX counts as one`,
};
const WITHIN_HINT =
  "Only the network fee is recorded: it's a disposal of your oldest coins at the fee's value (Form 8949, " +
  "box I or L; C or F before 2025). Your coins, their dates and cost basis stay as they are.";
// Between two exchanges BitcoinTX pools, it can't tell which one later sells
const BETWEEN_EXCHANGES_HINT =
  "A later sale at the exchange the coins moved to usually shows no basis on its 1099-DA: set that sale's " +
  "Broker form to Proceeds only.";

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
      deps={["amountTo"]}
    >
      {within && <small className="field-hint">{WITHIN_HINT}</small>}
      {within && kind === "exchange" && <small className="field-hint">{BETWEEN_EXCHANGES_HINT}</small>}
      {!within && accountKind(book, toId) === "wallet" && <small className="field-hint">{ONE_WALLET_HINT}</small>}
    </AccountPicker>
  );
};

/**
 * A transfer between the user's accounts: the destination within the
 * source's currency (a bitcoin one can also be the same account, a
 * consolidation), and the fee is what was sent less what arrived, in
 * bitcoin or in dollars (#447; useFieldAutofill).
 */
const TransferFields: React.FC<{ book: AccountBook }> = ({ book }) => {
  const { register, watch, formState: { errors } } = useFormContext<TransactionFormData>();
  const fromId = chosenId(watch("fromAccountId"));
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
      >
        {accountKind(book, fromId) === "wallet" && <small className="field-hint">{ONE_WALLET_HINT}</small>}
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
    </>
  );
};

export default TransferFields;
