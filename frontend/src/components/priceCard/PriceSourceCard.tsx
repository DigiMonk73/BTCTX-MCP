import React from "react";
import { useToast } from "../../contexts/useToast";
import { CONFIRM_WHY, FOOTER, cardView, type NetworkSettingsData } from "../../utils/priceSource";
import { historyLine, statusLine, type PriceStatus, type StatusLine } from "../../utils/priceStatus";
import EditableChoices from "./EditableChoices";
import MempoolTrust from "./MempoolTrust";
import ReadOnlyChoices from "./ReadOnlyChoices";
import { usePriceCard } from "./usePriceCard";
import "../../styles/priceCard.css";

interface Props {
  /** "first-run": the question on the Dashboard until a choice is saved (or confirmed). */
  variant: "first-run" | "settings";
}

const ICONS = { ok: "●", idle: "○", warning: "▲" } as const;
const LOADING: StatusLine = { tone: "idle", text: "Loading…" };

function lineFor(status: PriceStatus | null, saved: NetworkSettingsData): StatusLine {
  const ctx = { backup: saved.mempool_fallback, tor: Boolean(saved.proxy_url), trustable: saved.mempool_trustable };
  return status ? statusLine(status, ctx) : LOADING;
}

/** The hourly history's line, first on the card, with the download's progress (#145). */
const History: React.FC<{ status: PriceStatus | null; tor: boolean }> = ({ status, tor }) => {
  const line = status ? historyLine(status, { backup: false, tor }) : null;
  if (!line) return null;
  return (
    <div className={`price-history ${line.tone}`}>
      <p className="price-history-text">
        {line.tone === "ok" && <span aria-hidden="true">✓ </span>}
        {line.tone === "warning" && <span aria-hidden="true">▲ </span>}
        {line.text}
      </p>
      {line.progress && (
        <progress
          className="price-progress"
          value={line.progress.done}
          max={line.progress.total}
          aria-label="Hourly history downloaded"
          aria-valuetext={`${line.progress.done} of ${line.progress.total} years`}
        />
      )}
    </div>
  );
};

/**
 * Where BitcoinTX gets Bitcoin prices (#145): one card, the same words in
 * the first-run question and in Settings › Privacy & network, read-only
 * when the server sets it, and asking once to confirm a choice made before
 * it kept a record (2.9). Saving updates the page in place.
 */
const PriceSourceCard: React.FC<Props> = ({ variant }) => {
  const toast = useToast();
  const { saved, form, set, status, errors, saving, save, applied } = usePriceCard();
  if (!saved) return null;

  const firstRun = variant === "first-run";
  const view = cardView(saved, form, firstRun);
  const line = lineFor(status, saved);
  const Heading = firstRun ? "h2" : "h4"; // in Settings, under its section's h3

  const onSave = async () => {
    const result = await save(firstRun ? "first-run" : "settings");
    if (result.ok) toast.success(firstRun ? "Saved: BitcoinTX now knows where to get prices." : "Price source saved.");
    else if (result.message) toast.error(result.message); // and under its field, if it's about one
  };

  return (
    <section className={`price-card${firstRun ? " card first-run" : ""}`} aria-labelledby="price-card-title">
      <Heading id="price-card-title" className="price-card-title">
        {view.title}
      </Heading>
      {view.confirming && <p className="price-help">{CONFIRM_WHY}</p>}
      {/* While confirming nothing is downloaded, and the window must fit (800 × 600) */}
      {!view.confirming && <History status={status} tor={Boolean(saved.proxy_url)} />}
      {saved.managed ? (
        <ReadOnlyChoices settings={saved} />
      ) : (
        <EditableChoices
          form={form}
          set={set}
          errors={errors}
          current={view.current}
          history={status?.history}
          tor={{ fromServer: saved.tor_from_server === true, onStartOS: saved.host === "startos" }}
        />
      )}
      <p className={`price-status ${line.tone}`} role="status">
        <span aria-hidden="true">{ICONS[line.tone]}</span> {line.text}
      </p>
      <MempoolTrust saved={saved} status={status} onChange={applied} />
      {view.when && <p className="price-help">{view.when}</p>}
      {!view.confirming && <p className="price-footer">{FOOTER}</p>}
      {!saved.managed && (
        <div className="price-actions">
          <button
            type="button"
            className="btn btn-primary"
            onClick={onSave}
            disabled={saving || !view.canSave}
            aria-describedby={view.blocked ? "price-blocked" : undefined}
          >
            {saving ? "Saving…" : view.label}
          </button>
          {view.blocked && (
            <span id="price-blocked" className="price-help">
              {view.blocked}
            </span>
          )}
        </div>
      )}
    </section>
  );
};

export default PriceSourceCard;
