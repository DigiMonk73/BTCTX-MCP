/* FILE: src/utils/format.ts */

/**
 * Utility module for formatting and parsing data in the BitcoinTX application.
 * Provides functions to handle:
 *  - decimal parsing,
 *  - numeric/currency formatting,
 *  - date/time formatting,
 *  - transaction/gains parsing (based on global domain types).
 */

/**
 * --------------------------------------------------------------------------
 * 1) Decimal Parsing
 * --------------------------------------------------------------------------
 */

/**
 * Safely parse a string (or number) into a JavaScript number.
 *  - Handles backend responses where numeric fields might be strings
 *    (e.g. "50.00000000").
 *  - Returns the number if already numeric, otherwise parseFloat.
 *  - Defaults to 0 if invalid, null, or undefined.
 */
export function parseDecimal(value?: string | number): number {
  if (value == null) return 0;
  if (typeof value === "number") return value;
  const parsed = parseFloat(value);
  return Number.isNaN(parsed) ? 0 : parsed;
}

/**
 * --------------------------------------------------------------------------
 * 2) Numeric Formatting
 * --------------------------------------------------------------------------
 */

/**
 * Format a number as USD with 2 decimal places.
 *  - e.g. 50 => "$50.00"
 */
export function formatUsd(amount: number): string {
  return `$${amount.toFixed(2)}`;
}

/**
 * Format a number as BTC with up to 8 decimal places.
 *  - e.g. 0.12345678 => "0.12345678 BTC"
 */
export function formatBtc(amount: number): string {
  return `${amount.toFixed(8)} BTC`;
}

/**
 * --------------------------------------------------------------------------
 * 3) Date/Time Formatting
 * --------------------------------------------------------------------------
 */

/**
 * Format an ISO timestamp into a human-readable string.
 *  - e.g. "2025-02-26T12:00:00Z" => "Feb 26, 2025, 12:00 PM"
 */
export function formatTimestamp(isoString: string): string {
  if (!isoString) return "Invalid Date";
  const d = new Date(isoString);
  if (isNaN(d.getTime())) return "Invalid Date";
  return d.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

/**
 * --------------------------------------------------------------------------
 * 4) Parsing Helpers for Transaction / GainsAndLosses
 * --------------------------------------------------------------------------
 *
 * These helpers transform raw backend data (ITransactionRaw, GainsAndLossesRaw)
 * into type-safe, UI-ready formats (ITransaction, GainsAndLosses).
 *
 * No local interface definitions needed — we import them from global.d.ts.
 */

/**
 * parseTransaction:
 *  - Converts string-based numeric fields (e.g. "50.00000000") to numbers
 *  - Normalizes null => undefined for optional strings
 *  - Returns an object conforming to ITransaction
 */
export function parseTransaction(rawTx: ITransactionRaw): ITransaction {
  return {
    id: rawTx.id,
    from_account_id: rawTx.from_account_id,
    to_account_id: rawTx.to_account_id,
    type: rawTx.type,
    timestamp: rawTx.timestamp,
    is_locked: rawTx.is_locked,

    // Numeric fields
    amount: parseDecimal(rawTx.amount),
    fee_amount: parseDecimal(rawTx.fee_amount),
    cost_basis_usd: parseDecimal(rawTx.cost_basis_usd),
    proceeds_usd: parseDecimal(rawTx.proceeds_usd),
    gross_proceeds_usd: parseDecimal(rawTx.gross_proceeds_usd),
    fmv_usd: parseDecimal(rawTx.fmv_usd),
    realized_gain_usd: parseDecimal(rawTx.realized_gain_usd),

    // Optional fields normalized
    holding_period: rawTx.holding_period ?? undefined,
    external_ref: rawTx.external_ref ?? undefined,
    source: rawTx.source ?? undefined,
    purpose: rawTx.purpose ?? undefined,
    broker_reporting: rawTx.broker_reporting ?? null,
    fee_currency: rawTx.fee_currency ?? undefined,
    created_at: rawTx.created_at ?? undefined,
    updated_at: rawTx.updated_at ?? undefined,
  };
}

/**
 * parseGainsAndLosses:
 *  - Parses raw GainsAndLosses data into numeric format.
 *  - Ensures all fields are real numbers, defaulting to 0 if missing.
 *
 * Note:
 *  - We keep older fields (short_term_realized_gains, etc.) for backward
 *    compatibility.
 *  - We also add new fields for detailed short-term vs. long-term gains/losses.
 *  - And now we also parse the new BTC fields (income_btc, interest_btc, etc.).
 */
export function parseGainsAndLosses(raw: GainsAndLossesRaw): GainsAndLosses {
  return {
    // ------------------ Existing or legacy fields ------------------
    sells_proceeds: parseDecimal(raw.sells_proceeds),
    withdrawals_spent: parseDecimal(raw.withdrawals_spent),
    income_earned: parseDecimal(raw.income_earned),
    interest_earned: parseDecimal(raw.interest_earned),
    rewards_earned: parseDecimal(raw.rewards_earned),
    gifts_received: parseDecimal(raw.gifts_received),
    realized_gains: parseDecimal(raw.realized_gains),
    total_income: parseDecimal(raw.total_income),

    // Fees are nested; parse both USD & BTC
    fees: {
      USD: parseDecimal(raw.fees?.USD),
      BTC: parseDecimal(raw.fees?.BTC),
    },

    // total_gains & total_losses still exist for older code references
    total_gains: parseDecimal(raw.total_gains),
    total_losses: parseDecimal(raw.total_losses),

    // Backward compatibility: older short/long fields
    short_term_realized_gains: parseDecimal(raw.short_term_realized_gains),
    long_term_realized_gains: parseDecimal(raw.long_term_realized_gains),
    total_realized_gains_usd: parseDecimal(raw.total_realized_gains_usd),

    // ------------------ New short/long breakdown fields ------------------
    short_term_gains: parseDecimal(raw.short_term_gains),
    short_term_losses: parseDecimal(raw.short_term_losses),
    short_term_net: parseDecimal(raw.short_term_net),

    long_term_gains: parseDecimal(raw.long_term_gains),
    long_term_losses: parseDecimal(raw.long_term_losses),
    long_term_net: parseDecimal(raw.long_term_net),

    // Overall net gains across short & long
    total_net_capital_gains: parseDecimal(raw.total_net_capital_gains),

    // ------------------ New BTC fields for Income/Interest/Rewards/Gifts ------------------
    income_btc: parseDecimal(raw.income_btc),
    interest_btc: parseDecimal(raw.interest_btc),
    rewards_btc: parseDecimal(raw.rewards_btc),
    gifts_btc: parseDecimal(raw.gifts_btc),

    // ------------------ New YTD Gains field ------------------
    year_to_date_capital_gains: parseDecimal(raw.year_to_date_capital_gains),
  };
}
