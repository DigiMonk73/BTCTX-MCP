import React, { useEffect } from "react";
import { useFormContext } from "react-hook-form";
import {
  accountCurrency,
  accountKind,
  accountName,
  chosenId,
  isBtcAccount,
  transferTargets,
  visibleAccounts,
} from "../../utils/accounts";
import { ONE_WALLET_HINT } from "../../utils/disclaimer";
import { btcText, parseDecimal } from "../../utils/format";
import { dollarTransferFee, transferAmountProblem } from "../../utils/transferAmounts";
import AccountPicker from "./AccountPicker";
import FeeValueField from "./FeeValueField";

const WITHIN_HINT =
  "Only the network fee is recorded: it's a disposal of your oldest coins at the fee's value (Form 8949, " +
  "box I or L; C or F before 2025). Your coins, their dates and cost basis stay as they are.";
// Between two exchanges BitcoinTX pools, it can't tell which one later sells
const BETWEEN_EXCHANGES_HINT =
  "A later sale at the exchange the coins moved to usually shows no basis on its 1099-DA: set that sale's " +
  "Broker form to Proceeds only.";

/** What left less what arrived. A bitcoin fee stays plain sats
 * ("0.00000014", never "1.4e-7", #101); a dollar fee is the cent figure
 * the save sends (0.30 and 0.10 are 0.2, #447). The effect depends on the
 * currency string, never the book, so a new book object can't loop it. */
function useTransferFee(book: AccountBook): void {
  const { watch, setValue } = useFormContext<TransactionFormData>();
  const currency = accountCurrency(book, chosenId(watch("fromAccountId")));
  const amountFrom = parseDecimal(watch("amountFrom")) || 0;
  const amountTo = parseDecimal(watch("amountTo")) || 0;

  useEffect(() => {
    if (currency === "BTC") {
      const fee = amountFrom - amountTo;
      setValue("fee", fee < 0 ? 0 : btcText(fee)); // "0.00000014", never "1.4e-7" (#101)
    } else if (currency === "USD") {
      setValue("fee", Math.max(dollarTransferFee(amountFrom, amountTo), 0)); // the one the save sends (#447)
    }
  }, [currency, amountFrom, amountTo, setValue]);
}

/**
 * A transfer between the owner's accounts (5.13). To lists accounts of the
 * same currency; the same account is offered only when it holds bitcoin, as
 * a consolidation. The fee is what left less what arrived (#447, #159).
 */
const TransferFields: React.FC<{ book: AccountBook }> = ({ book }) => {
  const { register, watch, formState: { errors } } = useFormContext<TransactionFormData>();
  useTransferFee(book);
  const fromId = chosenId(watch("fromAccountId"));
  const toId = chosenId(watch("toAccountId"));
  const currency = accountCurrency(book, fromId);
  const within = toId === fromId && isBtcAccount(book, fromId);
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
        deps={["amountFrom", "amountTo"]}
      >
        {accountKind(book, fromId) === "wallet" && <small className="field-hint">{ONE_WALLET_HINT}</small>}
      </AccountPicker>

      <div className="field">
        <label htmlFor="tx-from-currency">From Currency</label>
        <input
          id="tx-from-currency"
          type="text"
          className="input"
          value={currency ?? ""}
          readOnly
        />
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
            validate: (_v, values) =>
              transferAmountProblem(values, accountCurrency(book, values.fromAccountId), "amountFrom") ?? true,
          })}
        />
        {errors.amountFrom && (
          <span className="field-error">{errors.amountFrom.message}</span>
        )}
      </div>

      <AccountPicker
        id="tx-to-account"
        label="To Account"
        field="toAccountId"
        book={book}
        choices={(saved) => transferTargets(book, fromId, saved)}
        placeholder="Select To Account"
        requiredMessage="To Account is required"
        optionLabel={(id) => (id === fromId ? `Consolidation: ${accountName(book, id)}` : accountName(book, id))}
        deps={["amountTo"]}
      >
        {within && (
          <>
            <small className="field-hint">{WITHIN_HINT}</small>
            {accountKind(book, fromId) === "exchange" && (
              <small className="field-hint">{BETWEEN_EXCHANGES_HINT}</small>
            )}
          </>
        )}
        {toId !== fromId && accountKind(book, toId) === "wallet" && (
          <small className="field-hint">{ONE_WALLET_HINT}</small>
        )}
      </AccountPicker>

      <div className="field">
        <label htmlFor="tx-to-currency">To Currency</label>
        <input
          id="tx-to-currency"
          type="text"
          className="input"
          value={accountCurrency(book, toId) ?? ""}
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
            validate: (_v, values) =>
              transferAmountProblem(values, accountCurrency(book, values.fromAccountId), "amountTo") ?? true,
          })}
        />
        {errors.amountTo && (
          <span className="field-error">{errors.amountTo.message}</span>
        )}
      </div>

      {currency === "BTC" ? (
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
