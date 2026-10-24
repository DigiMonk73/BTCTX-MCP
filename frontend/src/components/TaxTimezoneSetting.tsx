import React, { useEffect, useMemo, useState } from "react";
import { useToast } from "../contexts/useToast";
import {
  browserTimezone, canSaveTimezone, getTaxTimezone, setTaxTimezone, timezoneNotSaved, timezoneSuggestion,
  type TaxTimezone,
} from "../utils/taxTimezone";
import PastYearDialog from "./PastYearDialog";
import { usePastYearWarning } from "./transactionForm/usePastYearWarning";

/**
 * Settings row: the timezone used for tax dates — which tax year a
 * transaction falls in, Form 8949 dates, and holding-period anniversaries.
 * A timezone that changes an earlier tax year's figures is saved only once
 * the owner confirms it (2.0 spec 5.8). `onSaved` once one is: Ledger
 * Review gives its times and tax years in it (#645).
 */
const TaxTimezoneSetting: React.FC<{ onSaved?: () => void }> = ({ onSaved }) => {
  const toast = useToast();
  const pastYears = usePastYearWarning();
  const [taxTimezone, setTaxTimezoneState] = useState<TaxTimezone | null>(null);
  const current = taxTimezone?.timezone ?? "";
  const [selected, setSelected] = useState<string>("");
  const [saving, setSaving] = useState(false);

  const zones = useMemo(() => {
    const intl = Intl as unknown as { supportedValuesOf?: (key: string) => string[] };
    const all = intl.supportedValuesOf ? intl.supportedValuesOf("timeZone") : [];
    return Array.from(new Set(["UTC", browserTimezone(), ...all]));
  }, []);

  useEffect(() => {
    getTaxTimezone()
      .then((tz) => {
        setTaxTimezoneState(tz);
        setSelected(tz.timezone);
      })
      .catch(() => undefined);
  }, []);

  const save = async () => {
    setSaving(true);
    try {
      const tz = await pastYears.attempt("setting", (confirm) => setTaxTimezone(selected, confirm));
      if (tz === null) return; // cancelled: nothing saved
      setTaxTimezoneState(tz);
      onSaved?.();
      toast.success(`Tax timezone set to ${tz.timezone}. Gains were recalculated.`);
    } catch (err) {
      toast.error(timezoneNotSaved(err));
    } finally {
      setSaving(false);
    }
  };

  const suggestion = timezoneSuggestion(taxTimezone, browserTimezone());

  return (
    <div className="settings-option">
      <div className="option-info">
        <span className="settings-option-title">Tax Timezone</span>
        <p className="settings-option-subtitle">
          Decides which tax year a late-night Dec 31 transaction belongs to, the dates on
          Form 8949, and when a holding becomes long-term. Current: <strong>{current || "…"}</strong>
        </p>
        {suggestion && <p className="note" role="note">{suggestion}</p>}
      </div>
      <div className="credential-update-form">
        <select
          className="input"
          value={selected}
          onChange={(e) => setSelected(e.target.value)}
          aria-label="Tax timezone"
        >
          {zones.map((z) => (
            <option key={z} value={z}>
              {z === browserTimezone() ? `${z} (this computer)` : z}
            </option>
          ))}
        </select>
        <div className="credential-submit-container">
          <button
            className="btn btn-secondary"
            onClick={save}
            disabled={saving || !canSaveTimezone(taxTimezone, selected)}
          >
            {saving ? "Saving..." : "Save"}
          </button>
        </div>
      </div>
      {pastYears.question && <PastYearDialog {...pastYears.question} />}
    </div>
  );
};

export default TaxTimezoneSetting;
