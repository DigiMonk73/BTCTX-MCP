import React from "react";
import { useFormContext } from "react-hook-form";
import AccountAmountFields from "./AccountAmountFields";
import BtcWithdrawalValues from "./BtcWithdrawalValues";
import FeeValueField from "./FeeValueField";
import { isNotSold } from "../../utils/purposes";

/**
 * A withdrawal; a BTC one also has its purpose, the fee's USD value, its
 * proceeds, and for a gift, donation or loss its fair market value.
 */
const WithdrawalFields: React.FC = () => {
  const { register, watch } = useFormContext<TransactionFormData>();
  const account = watch("account");
  const currency = watch("currency");
  const purpose = watch("purpose");
  const showPurpose = account === "Wallet" || (account === "Exchange" && currency === "BTC");
  const isBtc = currency === "BTC";
  const notSold = isNotSold(purpose);

  return (
    <>
      <AccountAmountFields />

      {showPurpose && (
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
    </>
  );
};

export default WithdrawalFields;
