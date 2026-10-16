import React from "react";
import ValueOrigin from "./ValueOrigin";
import { useFormContext } from "react-hook-form";
import BrokerReportingField from "./BrokerReportingField";
import { useBlankPriceSource } from "./useBlankPriceSource";

/** A gift's, donation's or lost coins' fair market value: blank means that
 * hour's price, filled when it's saved (#255), as an income value is. */
const FmvField: React.FC<{ priced: string }> = ({ priced }) => {
  const { register, watch } = useFormContext<TransactionFormData>();
  const fmv = watch("fmv_usd");
  return (
    <div className="field">
      <label htmlFor="tx-fmv-usd">FMV (USD)</label>
      <input
        id="tx-fmv-usd"
        type="number"
        step="0.01"
        className="input"
        {...register("fmv_usd", { valueAsNumber: true })}
      />
      <small className="field-hint">
        {fmv == null || Number.isNaN(fmv)
          ? "Its fair market value when it left. Leave blank to use the BTC price when that hour began " +
            `(that day's, where there's no hourly price). ${priced}`.trim()
          : "Its fair market value when it left."}
      </small>
      <ValueOrigin fromPrice="fmvFromPrice" stored="fmvStored" shown="fmv_usd" />
    </div>
  );
};

/** A BTC withdrawal's proceeds (Spent: blank means that hour's price), the
 * broker form for a Spent one, the fair market value for the others (blank
 * means that hour's price too, #255). */
const BtcWithdrawalValues: React.FC<{ notSold: boolean }> = ({ notSold }) => {
  const { register, watch } = useFormContext<TransactionFormData>();
  const priced = useBlankPriceSource(); // where a blank value's price comes from (#208)
  const spent = watch("purpose") === "Spent";
  const proceeds = watch("proceeds_usd");
  const fee = watch("fee");
  return (
    <>
      <div className="field">
        <label htmlFor="tx-proceeds-usd">Proceeds (USD)</label>
        <input
          id="tx-proceeds-usd"
          type="number"
          step="0.01"
          className="input"
          {...register("proceeds_usd", { valueAsNumber: true })}
          readOnly={notSold}
        />
        {spent && (proceeds == null || Number.isNaN(proceeds)) && (
          <small className="field-hint">
            Leave blank to use the BTC price when that hour began as the proceeds (that day's, where
            there's no hourly price). {priced}
          </small>
        )}
        {spent && (proceeds ?? 0) > 0 && (fee ?? 0) > 0 && (
          <small className="field-hint">
            What you received, before the network fee: its value is taken off, as for a sale.
          </small>
        )}
        {spent && <ValueOrigin fromPrice="proceedsFromPrice" stored="proceedsStored" shown="proceeds_usd" />}
        {spent && proceeds === 0 && (
          <div className="field-warning">
            <strong>Warning:</strong> You selected "Spent" but "Proceeds (USD)" is 0.
          </div>
        )}
      </div>

      {spent && <BrokerReportingField />}

      {notSold && <FmvField priced={priced} />}
    </>
  );
};

export default BtcWithdrawalValues;
