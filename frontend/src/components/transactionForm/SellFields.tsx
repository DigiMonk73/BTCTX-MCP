import React from "react";
import { useFormContext } from "react-hook-form";
import { exchangeName, sellExchanges } from "../../utils/accounts";
import AccountPicker from "./AccountPicker";
import BrokerReportingField from "./BrokerReportingField";

/** A Sell on an exchange (from its BTC account, into its dollars): the BTC
 * sold, its gross proceeds and the fee. */
const SellFields: React.FC<{ book: AccountBook }> = ({ book }) => {
  const { register, formState: { errors } } = useFormContext<TransactionFormData>();
  return (
    <>
      <AccountPicker
        id="tx-account"
        label="Account"
        field="fromAccountId"
        book={book}
        choices={(saved) => sellExchanges(book, saved)}
        placeholder="Select Exchange"
        requiredMessage="Please select an exchange"
        optionLabel={(id) => exchangeName(book, id)}
      />

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
        <label htmlFor="tx-gross-proceeds-usd">Gross Proceeds (USD)</label>
        <input
          id="tx-gross-proceeds-usd"
          type="number"
          step="0.01"
          className="input"
          {...register("grossProceedsUSD", {
            required: true,
            valueAsNumber: true,
          })}
        />
        {errors.grossProceedsUSD && (
          <span className="field-error">Gross proceeds is required</span>
        )}
        <small className="field-hint">
          BitcoinTX takes the fee off to give the net proceeds.
        </small>
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

      <BrokerReportingField />
    </>
  );
};

export default SellFields;
