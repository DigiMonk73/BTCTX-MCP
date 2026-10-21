import React from "react";
import { useFormContext } from "react-hook-form";
import { accountKind, accountName, buyExchanges, buyPayers, exchangeName } from "../../utils/accounts";
import AccountPicker from "./AccountPicker";

/** A Buy: the dollars' account, then the exchange the bitcoin is bought into (5.13, Q15). */
const BuyFields: React.FC<{ book: AccountBook }> = ({ book }) => {
  const { register, watch, formState: { errors } } = useFormContext<TransactionFormData>();
  // A blank select is "" until setValueAs runs, so it is no payer (5.13).
  const watchedPayer = watch("fromAccountId");
  const payerId = typeof watchedPayer === "number" ? watchedPayer : undefined;
  return (
    <>
      <AccountPicker
        id="tx-from-account"
        label="Paid from"
        field="fromAccountId"
        book={book}
        choices={(saved) => buyPayers(book, saved)}
        placeholder="Select Account"
        requiredMessage="Please select an account"
        optionLabel={(id) => {
          const name = accountName(book, id);
          return accountKind(book, id) === "bank" ? `${name} (auto-buy)` : name;
        }}
      >
        <small className="field-hint">
          Select where the USD is coming from.
        </small>
      </AccountPicker>

      <AccountPicker
        id="tx-to-account"
        label="Exchange"
        field="toAccountId"
        book={book}
        choices={(saved) => buyExchanges(book, payerId, saved)}
        placeholder="Select Exchange"
        requiredMessage="Please select an exchange"
        optionLabel={(id) => exchangeName(book, id)}
      />

      <div className="field">
        <label htmlFor="tx-amount-usd">Amount USD</label>
        <input
          id="tx-amount-usd"
          type="number"
          step="0.01"
          className="input"
          {...register("amountUSD", {
            required: true,
            valueAsNumber: true,
          })}
        />
        {errors.amountUSD && (
          <span className="field-error">Amount USD is required</span>
        )}
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
        <label htmlFor="tx-fee-usd">Fee (USD)</label>
        <input
          id="tx-fee-usd"
          type="number"
          step="0.00000001"
          className="input"
          {...register("fee", { valueAsNumber: true })}
        />
      </div>
    </>
  );
};

export default BuyFields;
