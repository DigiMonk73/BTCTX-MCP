import React from "react";
import { useFormContext } from "react-hook-form";
import BrokerReportingField from "./BrokerReportingField";

/** A BTC withdrawal's proceeds (Spent: blank means that hour's price), the
 * broker form for a Spent one, the fair market value for the others. */
const BtcWithdrawalValues: React.FC<{ notSold: boolean; onRefreshFmv: () => void }> = ({
  notSold,
  onRefreshFmv,
}) => {
  const { register, watch } = useFormContext<TransactionFormData>();
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
            there's no hourly price).
          </small>
        )}
        {spent && (proceeds ?? 0) > 0 && (fee ?? 0) > 0 && (
          <small className="field-hint">
            What you received, before the network fee: its value is taken off, as for a sale.
          </small>
        )}
        {spent && proceeds === 0 && (
          <div className="field-warning">
            <strong>Warning:</strong> You selected "Spent" but "Proceeds (USD)" is 0.
          </div>
        )}
      </div>

      {spent && <BrokerReportingField />}

      {notSold && (
        <div className="field">
          <label htmlFor="tx-fmv-usd">FMV (USD)</label>
          <div className="form-input-row">
            <input
              id="tx-fmv-usd"
              type="number"
              step="0.01"
              className="input"
              {...register("fmv_usd", { valueAsNumber: true })}
            />
            <button
              type="button"
              onClick={onRefreshFmv}
              className="btn btn-secondary"
            >
              Refresh
            </button>
          </div>
          <small className="field-hint">
            Estimated fair market value at the time of gift/donation/lost.
          </small>
        </div>
      )}
    </>
  );
};

export default BtcWithdrawalValues;
