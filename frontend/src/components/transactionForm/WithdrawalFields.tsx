import React from "react";
import { useFormContext } from "react-hook-form";
import AccountAmountFields from "./AccountAmountFields";
import BtcWithdrawalValues from "./BtcWithdrawalValues";
import FeeValueField from "./FeeValueField";
import LeavingCoins from "./LeavingCoins";
import { chosenId } from "../../utils/accounts";
import { isNotSold } from "../../utils/purposes";
import { inBtcAccount } from "../../utils/transactionForm";

/**
 * A withdrawal; one from a bitcoin account also has its purpose, the fee's
 * USD value, its proceeds, and for a gift, donation or loss its fair market
 * value: only bitcoin leaving is spent, given, donated or lost (#449). From
 * one of your wallets, the coins that leave, which can be chosen (#711).
 */
const WithdrawalFields: React.FC<{ book: AccountBook; transactionId?: number | null }> = ({ book, transactionId }) => {
  const { register, watch } = useFormContext<TransactionFormData>();
  const isBtc = inBtcAccount({ type: "Withdrawal", fromAccountId: chosenId(watch("fromAccountId")) }, book);
  const purpose = watch("purpose");
  const notSold = isNotSold(purpose);

  return (
    <>
      <AccountAmountFields book={book} field="fromAccountId" />

      {isBtc && (
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
        <label htmlFor="tx-fee">{isBtc ? "Fee (BTC)" : "Fee (USD)"}</label>
        <input
          id="tx-fee"
          type="number"
          step="0.00000001"
          className="input"
          {...register("fee", { valueAsNumber: true })}
        />
      </div>
      {isBtc && <FeeValueField />}
      {isBtc && <BtcWithdrawalValues notSold={notSold} />}
      <LeavingCoins book={book} transactionId={transactionId} />
    </>
  );
};

export default WithdrawalFields;
