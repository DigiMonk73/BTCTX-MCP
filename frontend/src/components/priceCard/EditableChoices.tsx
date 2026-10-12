import React from "react";
import { PRICE_CHOICES, type PriceForm, type PriceSource } from "../../utils/priceSource";
import ChoiceFields from "./ChoiceFields";
import type { FieldErrors } from "./usePriceCard";

interface Props {
  form: PriceForm;
  set: (patch: Partial<PriceForm>) => void;
  errors: FieldErrors;
  /** While confirming (2.9): the stored choice, marked "Your current choice". */
  current: PriceSource | null;
}

/** The three choices as native radios in a fieldset, each one's fields right after it. */
const EditableChoices: React.FC<Props> = ({ form, set, errors, current }) => (
  <fieldset className="price-choices">
    <legend className="price-legend">Where should BitcoinTX get Bitcoin prices?</legend>
    {PRICE_CHOICES.map((c) => (
      <React.Fragment key={c.value}>
        <label className={form.source === c.value ? "price-choice chosen" : "price-choice"}>
          <input
            type="radio"
            name="price-source"
            value={c.value}
            checked={form.source === c.value}
            onChange={() => set({ source: c.value })}
            aria-describedby={`price-help-${c.value}`}
          />
          <span className="price-choice-text">
            <span className="price-choice-label">
              {c.label}
              {c.value === current && <span className="badge badge-accent">Your current choice</span>}
            </span>
            <span id={`price-help-${c.value}`} className="price-help">
              {c.help}
            </span>
          </span>
        </label>
        {form.source === c.value && <ChoiceFields form={form} set={set} errors={errors} />}
      </React.Fragment>
    ))}
  </fieldset>
);

export default EditableChoices;
