import React, { useCallback, useEffect, useState } from "react";
import api from "../api";

interface ReviewItem {
  id: number;
  date: string;
  type: string;
  purpose: string | null;
  source: string | null;
  amount: string;
  issue: string;
  change: string;
}

interface ReviewCheck {
  key: string;
  title: string;
  action: string;
  count: number;
  items: ReviewItem[];
}

interface LedgerReviewResponse {
  timezone: string;
  total: number;
  checks: ReviewCheck[];
}

/**
 * Settings section: the read-only Ledger review (GET /api/review) — saved
 * transactions worth a second look after an upgrade. It changes nothing;
 * the owner edits a transaction or runs Recalculate Ledger themselves.
 */
const LedgerReview: React.FC = () => {
  const [review, setReview] = useState<LedgerReviewResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setFailed(false);
    try {
      const res = await api.get<LedgerReviewResponse>("/review");
      setReview(res.data);
    } catch {
      setFailed(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const found = review?.checks.filter((c) => c.count > 0) ?? [];

  return (
    <div className="settings-section" role="region" aria-label="Ledger review">
      <h3>Ledger Review</h3>
      <div className="settings-option">
        <div className="option-info">
          <span className="settings-option-title">Transactions to check</span>
          <p className="settings-option-subtitle">
            Saved transactions worth a second look after an upgrade. Read-only: nothing here
            changes your ledger.
          </p>
        </div>
        <button onClick={load} disabled={loading} className="settings-button">
          {loading ? "Checking..." : "Check again"}
        </button>
      </div>
      {failed && <p className="settings-option-subtitle">Could not load the review.</p>}
      {review && review.total === 0 && (
        <p className="settings-option-subtitle">Nothing to review.</p>
      )}
      {found.map((check) => (
        <div key={check.key} className="ledger-review-check">
          <strong>
            {check.title}: {check.count}
          </strong>
          <ul aria-label={check.title}>
            {check.items.map((item) => (
              <li key={item.id}>
                #{item.id} · {item.date} · {item.type} (
                {item.type === "Deposit" ? item.source : item.purpose}) · {item.amount} BTC —{" "}
                {item.issue} {item.change}
              </li>
            ))}
          </ul>
          <p className="settings-option-subtitle">{check.action}</p>
        </div>
      ))}
      {review && review.total > 0 && (
        <p className="settings-option-subtitle">Dates in {review.timezone}.</p>
      )}
    </div>
  );
};

export default LedgerReview;
