import React from "react";
import { useFormContext } from "react-hook-form";

/** Form 1099-DA override (a Sell, or a Spent BTC withdrawal). */
const BrokerReportingField: React.FC = () => {
  const { register } = useFormContext<TransactionFormData>();
  return (
    <div className="field">
      <label htmlFor="tx-broker-reporting">Broker form (1099-DA / 1099-B)</label>
      <select id="tx-broker-reporting" className="input" {...register("brokerReporting")}>
        <option value="">Automatic</option>
        <option value="none">Not on a broker form</option>
        <option value="proceeds">Proceeds only (no basis)</option>
        <option value="basis">Proceeds and basis</option>
      </select>
      <small className="field-hint">
        Picks the Form 8949 box. Leave on Automatic unless the form your broker
        sent says otherwise.
      </small>
    </div>
  );
};

export default BrokerReportingField;
