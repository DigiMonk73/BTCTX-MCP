// The shapes GET /api/review returns (backend/services/review.py)

export interface ReviewItem {
  id: number;
  date: string;
  type: string;
  purpose: string | null;
  source: string | null;
  amount: string;
  issue: string;
  change: string;
  /** day_priced_values only: the item's tax year */
  year?: number;
}

/** day_priced_values: one tax year's transactions the hour would change, and the totals' change */
export interface HourlyYear {
  year: number;
  count: number;
  listed: number;
  ids: number[];
  income: string;
  basis: string;
  proceeds: string;
  fees: string;
}

export interface ReviewCheck {
  key: string;
  kind: "check" | "reminder";
  title: string;
  action: string;
  explanation: string[];
  count: number;
  items: ReviewItem[];
  years?: HourlyYear[];
}

export interface LedgerReviewResponse {
  timezone: string;
  /** Items that may point at a wrong figure; reminders aren't counted. */
  total: number;
  reminders: number;
  checks: ReviewCheck[];
  recalc_error?: string | null;
}

/** What POST /api/review/hourly-prices changes: these transactions, or a whole tax year's */
export type HourlyPick = { ids: number[] } | { year: number };
