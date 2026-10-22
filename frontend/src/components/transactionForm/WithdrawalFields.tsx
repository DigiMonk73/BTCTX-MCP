import React from "react";
import { useFormContext } from "react-hook-form";
import AccountAmountFields from "./AccountAmountFields";
import BtcWithdrawalValues from "./BtcWithdrawalValues";
import FeeValueField from "./FeeValueField";
import { chosenId, isBtcAccount } from "../../utils/accounts";
import { isNotSold } from "../../utils/purposes";

/**
 * A withdrawal; one from a bitcoin account also has its purpose, the fee's
 * USD value, its proceeds, and for a gift, donation or loss its fair market
 * value. Only bitcoin leaving is spent, given, donated or lost (#449).
 */
const WithdrawalFields: React.FC<{ book: AccountBook }> = ({ book }) => {
  const { register, watch } = useFormContext<TransactionFormData>();
  const btc = isBtcAccount(book, chosenId(watch("fromAccountId")));
  const purpose = watch("purpose");
  const notSold = isNotSold(purpose);

  return (
    <>
      <AccountAmountFields book={book} field="fromAccountId" />

      {btc && (
        <div className="field">
          <label htmlFor="tx-purpose">Purpose (BTC only)</label>
          <select
            id="tx-purpose"
            className="input"
            {...register("purpose", { required: true })}
          >
            <option value="">Select Purpose</option>
            <option value="Spent">Spent</option>
            <option value="Gift">Gift</option>
            <option value="Donation">Donation</option>
            <option value="Lost">Lost</option>
          </select>
        </div>
      )}

      <div className="field">
        <label htmlFor="tx-fee">{btc ? "Fee (BTC)" : "Fee (USD)"}</label>
        <input
          id="tx-fee"
          type="number"
          step="0.00000001"
          className="input"
          {...register("fee", { valueAsNumber: true })}
        />
      </div>
      {btc && <FeeValueField />}
      {btc && <BtcWithdrawalValues notSold={notSold} />}
    </>
  );
};

export default WithdrawalFields;
