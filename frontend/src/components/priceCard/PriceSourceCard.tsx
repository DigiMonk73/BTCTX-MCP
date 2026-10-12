import React from "react";
import { useToast } from "../../contexts/useToast";
import { FOOTER, PRICE_CHOICES, cannotSave, priceFormChanged } from "../../utils/priceSource";
import { statusLine } from "../../utils/priceStatus";
import ChoiceFields from "./ChoiceFields";
import ReadOnlyChoices from "./ReadOnlyChoices";
import { usePriceCard } from "./usePriceCard";
import "../../styles/priceCard.css";

interface Props {
  /** "first-run": the question on the Dashboard until a choice is saved. */
  variant: "first-run" | "settings";
}

const ICONS = { ok: "●", idle: "○", warning: "▲" } as const;

/**
 * Where BitcoinTX gets Bitcoin prices (#145): one card, the same words in
 * the first-run question and in Settings › Privacy & network, read-only
 * when the server sets it. Saving updates the page in place.
 */
const PriceSourceCard: React.FC<Props> = ({ variant }) => {
  const toast = useToast();
  const { saved, form, set, status, timezone, errors, saving, save } = usePriceCard();
  if (!saved) return null;

  const managed = saved.managed === true;
  const line = status
    ? statusLine(status, { backup: saved.mempool_fallback, tor: Boolean(saved.proxy_url), timezone })
    : { tone: "idle" as const, text: "Loading…" };
  const blocked = cannotSave(form);
  const firstRun = variant === "first-run";
  const Heading = firstRun ? "h2" : "h4"; // in Settings, under its section's h3

  const onSave = async () => {
    const result = await save();
    if (result.ok) toast.success(firstRun ? "Saved: BitcoinTX now knows where to get prices." : "Price source saved.");
    else if (result.message) toast.error(result.message); // and under its field, if it's about one
  };

  return (
    <section className={`price-card${firstRun ? " card first-run" : ""}`} aria-labelledby="price-card-title">
      <Heading id="price-card-title" className="price-card-title">
        Bitcoin prices
      </Heading>
      {managed ? (
        <ReadOnlyChoices settings={saved} />
      ) : (
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
                  <span className="price-choice-label">{c.label}</span>
                  <span id={`price-help-${c.value}`} className="price-help">
                    {c.help}
                  </span>
                </span>
              </label>
              {form.source === c.value && <ChoiceFields form={form} set={set} errors={errors} />}
            </React.Fragment>
          ))}
        </fieldset>
      )}
      <p className={`price-status ${line.tone}`} role="status">
        <span aria-hidden="true">{ICONS[line.tone]}</span> {line.text}
      </p>
      <p className="price-footer">{FOOTER}</p>
      {!managed && (
        <div className="price-actions">
          <button
            type="button"
            className="btn btn-primary"
            onClick={onSave}
            disabled={saving || blocked !== null || !priceFormChanged(saved, form)}
            aria-describedby={blocked && form.source !== "" ? "price-blocked" : undefined}
          >
            {saving ? "Saving…" : firstRun ? "Use this" : "Save"}
          </button>
          {blocked && form.source !== "" && (
            <span id="price-blocked" className="price-help">
              {blocked}
            </span>
          )}
        </div>
      )}
    </section>
  );
};

export default PriceSourceCard;
