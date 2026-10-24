import React from "react";
import { useFormContext } from "react-hook-form";
import {
  accountKind, accountName, buyExchanges, buyPayers, chosenId, exchangeCount, exchangeName,
} from "../../utils/accounts";
import AccountPicker from "./AccountPicker";

/**
 * A Buy: the exchange whose BTC account the bitcoin goes into, then the
 * dollars that paid for it, that exchange's or a bank's (an auto-buy): an
 * exchange's dollars buy only on that exchange (5.5, Q15). With one
 * exchange its choice isn't shown, as in 1.x.
 */
const BuyFields: React.FC<{ book: AccountBook }> = ({ book }) => {
  const { register, watch, formState: { errors } } = useFormContext<TransactionFormData>();
  const exchangeId = chosenId(watch("toAccountId"));
  return (
    <>
      <AccountPicker
        id="tx-to-account"
        label="Exchange"
        field="toAccountId"
        book={book}
        choices={(saved) => buyExchanges(book, saved)}
        placeholder="Select Exchange"
        requiredMessage="Please select an exchange"
        optionLabel={(id) => exchangeName(book, id)}
        quietWhenFixed={exchangeCount(book) === 1}
      />

      <AccountPicker
        id="tx-from-account"
        label="Paid from"
        field="fromAccountId"
        book={book}
        choices={(saved) => buyPayers(book, exchangeId, saved)}
        placeholder={exchangeId === undefined ? "Choose the exchange first" : "Select Account"}
        requiredMessage="Please select an account"
        optionLabel={(id) => (accountKind(book, id) === "bank" ? `${accountName(book, id)} (auto-buy)` : accountName(book, id))}
      >
        <small className="field-hint">
          Select where the USD is coming from.
        </small>
      </AccountPicker>

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
