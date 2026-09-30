/**
 * Numbers and dates as the app shows them, and the server's answers turned
 * into numbers (the API sends most amounts as strings, "50.00000000").
 */

/** A decimal from the API (a string or a number) as a number; 0 when it is
 * missing or unreadable text. */
export function parseDecimal(value?: string | number): number {
  if (value == null) return 0;
  if (typeof value === "number") return value;
  const parsed = parseFloat(value);
  return Number.isNaN(parsed) ? 0 : parsed;
}

/**
 * A number the user may leave blank: null for blank (undefined, null, "" or
 * NaN, which is what an empty number input gives), so the API can tell
 * "not given" from 0.
 */
export function optionalDecimal(value?: string | number | null): number | null {
  if (value == null || value === "") return null;
  const n = typeof value === "number" ? value : parseFloat(value);
  return Number.isNaN(n) ? null : n;
}

/** USD to the cent: 50 => "$50.00". */
export function formatUsd(amount: number): string {
  const abs = Math.abs(amount).toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  // A real minus sign (U+2212), and none on an amount that rounds to 0.00.
  const negative = amount < 0 && abs !== "0.00";
  return `${negative ? "\u2212" : ""}$${abs}`;
}

/**
 * USD with its sign always shown, for gains and losses.
 *  - e.g. 1373.21 => "+$1,373.21", -1373.21 => "−$1,373.21", 0 => "$0.00"
 */
export function formatSignedUsd(amount: number): string {
  const text = formatUsd(amount);
  return amount > 0 && text !== "$0.00" ? `+${text}` : text;
}

/** BTC to the satoshi: 0.12345678 => "0.12345678 BTC". */
export function formatBtc(amount: number): string {
  return `${amount.toFixed(8)} BTC`;
}

/** A date and time as the browser's locale writes them (the import
 * previews). */
export function formatLocalDateTime(dateStr: string): string {
  return new Date(dateStr).toLocaleString();
}

/** A transaction from the API with its amounts as numbers; a missing text
 * field is undefined rather than null. */
export function parseTransaction(rawTx: ITransactionRaw): ITransaction {
  return {
    id: rawTx.id,
    from_account_id: rawTx.from_account_id,
    to_account_id: rawTx.to_account_id,
    type: rawTx.type,
    timestamp: rawTx.timestamp,

    amount: parseDecimal(rawTx.amount),
    fee_amount: parseDecimal(rawTx.fee_amount),
    cost_basis_usd: parseDecimal(rawTx.cost_basis_usd),
    proceeds_usd: parseDecimal(rawTx.proceeds_usd),
    gross_proceeds_usd: parseDecimal(rawTx.gross_proceeds_usd),
    fmv_usd: parseDecimal(rawTx.fmv_usd),
    realized_gain_usd: parseDecimal(rawTx.realized_gain_usd),

    holding_period: rawTx.holding_period ?? undefined,
    external_ref: rawTx.external_ref ?? undefined,
    source: rawTx.source ?? undefined,
    purpose: rawTx.purpose ?? undefined,
    broker_reporting: rawTx.broker_reporting ?? null,
    fee_usd: rawTx.fee_usd == null ? null : parseDecimal(rawTx.fee_usd),
    fee_usd_manual: rawTx.fee_usd_manual ?? false,
    fee_currency: rawTx.fee_currency ?? undefined,
    created_at: rawTx.created_at ?? undefined,
    updated_at: rawTx.updated_at ?? undefined,
  };
}

/** The gains-and-losses answer with every figure as a number (0 when
 * missing). */
export function parseGainsAndLosses(raw: GainsAndLossesRaw): GainsAndLosses {
  return {
    sells_proceeds: parseDecimal(raw.sells_proceeds),
    withdrawals_spent: parseDecimal(raw.withdrawals_spent),
    income_earned: parseDecimal(raw.income_earned),
    interest_earned: parseDecimal(raw.interest_earned),
    rewards_earned: parseDecimal(raw.rewards_earned),
    gifts_received: parseDecimal(raw.gifts_received),
    total_income: parseDecimal(raw.total_income),
    fees: {
      USD: parseDecimal(raw.fees?.USD),
      BTC: parseDecimal(raw.fees?.BTC),
    },
    total_losses: parseDecimal(raw.total_losses),

    short_term_gains: parseDecimal(raw.short_term_gains),
    short_term_losses: parseDecimal(raw.short_term_losses),
    short_term_net: parseDecimal(raw.short_term_net),
    long_term_gains: parseDecimal(raw.long_term_gains),
    long_term_losses: parseDecimal(raw.long_term_losses),
    long_term_net: parseDecimal(raw.long_term_net),
    total_net_capital_gains: parseDecimal(raw.total_net_capital_gains),

    income_btc: parseDecimal(raw.income_btc),
    interest_btc: parseDecimal(raw.interest_btc),
    rewards_btc: parseDecimal(raw.rewards_btc),
    gifts_btc: parseDecimal(raw.gifts_btc),

    year_to_date_capital_gains: parseDecimal(raw.year_to_date_capital_gains),
  };
}
