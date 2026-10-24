import React, { useCallback, useEffect, useState } from "react";
import api from "../api";
import { showTheList } from "../utils/reminderList";
import { reviewAmount, typeWithSourceOrPurpose } from "../utils/transactionList";
import HourlyCheck from "./ledgerReview/HourlyCheck";
import type { HourlyPick, LedgerReviewResponse, ReviewCheck } from "./ledgerReview/types";

interface HourlyResult {
  changed: { id: number }[];
  backup: string | null;
  recalculated: boolean;
}

const ReviewItems: React.FC<{ check: ReviewCheck }> = ({ check }) => (
  <ul aria-label={check.title}>
    {check.items.map((item) => (
      <li key={item.id}>
        #{item.id} · {item.date} · {typeWithSourceOrPurpose(item)} · {reviewAmount(item)} —{" "}
        {item.issue} {item.change}
      </li>
    ))}
  </ul>
);

/**
 * A reminder (#128): its rows aren't errors, so one explanation for
 * the group and the list folded until asked for. Nothing is saved: the
 * deposits' group shrinks as the owner edits them; the sales' (#349)
 * stays, since nothing in the ledger is wrong.
 */
const ReminderGroup: React.FC<{ check: ReviewCheck }> = ({ check }) => {
  const [open, setOpen] = useState(false);
  return (
    <div className="ledger-review-check">
      <strong>
        {check.title}: {check.count}
      </strong>
      {check.explanation.map((paragraph) => (
        <p key={paragraph} className="settings-option-subtitle">
          {paragraph}
        </p>
      ))}
      <p className="settings-option-subtitle">{check.action}</p>
      <button onClick={() => setOpen(!open)} className="btn btn-secondary">
        {open ? "Hide the list" : showTheList(check.key, check.count)}
      </button>
      {open && <ReviewItems check={check} />}
    </div>
  );
};

interface LedgerReviewProps {
  /** Each answer, or null when the review failed: the section's summary (#355). A stable function. */
  onReview?: (review: LedgerReviewResponse | null) => void;
}

/**
 * Settings section: the Ledger review (GET /api/review) — saved
 * transactions worth a second look after an upgrade. Looking changes
 * nothing; the owner edits a transaction or runs Recalculate Ledger
 * themselves, or applies the hourly check's values (#144).
 */
const LedgerReview: React.FC<LedgerReviewProps> = ({ onReview }) => {
  const [review, setReview] = useState<LedgerReviewResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setFailed(false);
    try {
      const res = await api.get<LedgerReviewResponse>("/review");
      setReview(res.data);
      onReview?.(res.data);
    } catch {
      setFailed(true);
      onReview?.(null);
    } finally {
      setLoading(false);
    }
  }, [onReview]);

  useEffect(() => {
    void load();
  }, [load]);

  // Only the hourly check applies anything: it asks first (HourlyCheck)
  // Its outcome stays shown after the review reloads (load() clears `failed`)
  const applyHourly = async (pick: HourlyPick, question: string): Promise<boolean> => {
    if (!window.confirm(question)) return false;
    setLoading(true);
    setNotice(null);
    let applied = false;
    try {
      const { data } = await api.post<HourlyResult>("/review/hourly-prices", pick);
      const n = data.changed.length;
      setNotice(!data.recalculated ? "Nothing changed: those values are already at that price." :
        `Changed ${n} transaction${n === 1 ? "" : "s"} and recalculated the ledger` +
        (data.backup ? `; the copy from before is backups/${data.backup} in BitcoinTX's data folder.` : "."));
      applied = true;
    } catch {
      setNotice("The apply failed, or its answer didn't arrive: the review below shows the ledger as it is now.");
    } finally {
      setLoading(false);
    }
    await load();
    return applied;
  };

  const found = review?.checks.filter((c) => c.count > 0 && c.kind === "check") ?? [];
  const reminders = review?.checks.filter((c) => c.count > 0 && c.kind === "reminder") ?? [];

  return (
    <>
      <div className="settings-option">
        <div className="option-info">
          <span className="settings-option-title">Transactions to check</span>
          <p className="settings-option-subtitle">
            Saved transactions worth a second look after an upgrade. Looking changes nothing:
            only what you apply below does, after asking.
          </p>
        </div>
        <button onClick={load} disabled={loading} className="btn btn-secondary">
          {loading ? "Checking..." : "Check again"}
        </button>
      </div>
      {failed && <p className="settings-option-subtitle">The review could not be loaded.</p>}
      {notice && <p className="settings-option-subtitle">{notice}</p>}
      {review?.recalc_error && (
        <p className="settings-option-subtitle">
          Recalculate Ledger would stop with: {review.recalc_error}
        </p>
      )}
      {review && review.total === 0 && (
        <p className="settings-option-subtitle">
          {review.reminders > 0 ? "Nothing looks wrong." : "Nothing to review."}
        </p>
      )}
      {found.map((check) =>
        check.key === "day_priced_values" ? (
          <HourlyCheck key={check.key} check={check} busy={loading} onApply={applyHourly} />
        ) : (
          <div key={check.key} className="ledger-review-check">
            <strong>
              {check.title}: {check.count}
            </strong>
            <ReviewItems check={check} />
            <p className="settings-option-subtitle">{check.action}</p>
          </div>
        ),
      )}
      {reminders.map((check) => (
        <ReminderGroup key={check.key} check={check} />
      ))}
      {review && review.total + review.reminders > 0 && (
        <p className="settings-option-subtitle">Dates in {review.timezone}.</p>
      )}
    </>
  );
};

export default LedgerReview;
