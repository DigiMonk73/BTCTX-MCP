import React from "react";
import { useFormContext } from "react-hook-form";
import { accountCurrency, accountKind, chosenId, visibleAccounts } from "../../utils/accounts";
import { ONE_WALLET_HINT } from "../../utils/disclaimer";
import AccountPicker from "./AccountPicker";

/**
 * A Deposit's or Withdrawal's account, the currency that account holds, and
 * the amount. The currency is the account's, read from the book, so a dollar
 * deposit into a bitcoin account can't be built (D1).
 */
const AccountAmountFields: React.FC<{ book: AccountBook; field: "fromAccountId" | "toAccountId" }> = ({
  book,
  field,
}) => {
  const { register, watch, formState: { errors } } = useFormContext<TransactionFormData>();
  const chosen = chosenId(watch(field));
  return (
    <>
      <AccountPicker
        id="tx-account"
        label="Account"
        field={field}
        book={book}
        choices={(saved) => visibleAccounts(book, saved)}
        placeholder="Select Account"
        requiredMessage="Please select an account"
      >
        {accountKind(book, chosen) === "wallet" && <small className="field-hint">{ONE_WALLET_HINT}</small>}
      </AccountPicker>

      <div className="field">
        <label htmlFor="tx-currency">Currency</label>
        <input
          id="tx-currency"
          type="text"
          className="input"
          value={accountCurrency(book, chosen) ?? ""}
          readOnly
        />
      </div>

      <div className="field">
        <label htmlFor="tx-amount">Amount</label>
        <input
          id="tx-amount"
          type="number"
          step="0.00000001"
          className="input"
          {...register("amount", {
            required: true,
            valueAsNumber: true,
          })}
        />
        {errors.amount && (
          <span className="field-error">Amount is required</span>
        )}
      </div>
    </>
  );
};

export default AccountAmountFields;
