// Types shared across the app: the server's answers, the transaction form,
// and the Mac app's webview.

declare global {
  // The Mac app's webview (pywebview)
  interface PyWebViewSaveResult {
    success: boolean;
    path?: string;
    error?: string;
  }

  interface PyWebViewAPI {
    /** Shows the native Save dialog and writes the file (base64 content). */
    save_file(
      filename: string,
      data_base64: string,
      file_type: string
    ): Promise<PyWebViewSaveResult>;

    is_desktop(): Promise<boolean>;

    /** The first-run setup code while the account has the default login,
     * else null (desktop/desktop_api.py). Absent in a build before it. */
    setup_code?(): Promise<string | null>;
  }

  interface Window {
    pywebview?: {
      api: PyWebViewAPI;
    };
  }

  // The dashboard's figures
  interface AccountBalance {
    account_id: number;
    name: string;
    currency: string;
    balance: number | string; // parseDecimal
  }

  interface AverageCostBasis {
    averageCostBasis: number;
  }

  // GET /api/calculations/gains-and-losses
  interface GainsAndLossesRaw {
    sells_proceeds?: string | number;
    withdrawals_spent?: string | number;
    income_earned?: string | number;
    interest_earned?: string | number;
    rewards_earned?: string | number;
    gifts_received?: string | number;
    rebates_received?: string | number;
    total_income?: string | number;
    fees?: {
      USD?: string | number;
      BTC?: string | number;
    };
    total_losses?: string | number;

    short_term_gains?: string | number;
    short_term_losses?: string | number;
    short_term_net?: string | number;
    long_term_gains?: string | number;
    long_term_losses?: string | number;
    long_term_net?: string | number;
    total_net_capital_gains?: string | number;

    // The BTC received as income, interest, rewards, gifts and rebates
    income_btc?: string | number;
    interest_btc?: string | number;
    rewards_btc?: string | number;
    gifts_btc?: string | number;
    rebates_btc?: string | number;

    year_to_date_capital_gains?: string | number;
  }

  interface GainsAndLosses {
    sells_proceeds: number;
    withdrawals_spent: number;
    income_earned: number;
    interest_earned: number;
    rewards_earned: number;
    gifts_received: number;
    rebates_received: number;
    total_income: number;
    fees: {
      USD: number;
      BTC: number;
    };
    total_losses: number;

    short_term_gains: number;
    short_term_losses: number;
    short_term_net: number;
    long_term_gains: number;
    long_term_losses: number;
    long_term_net: number;
    total_net_capital_gains: number;

    income_btc: number;
    interest_btc: number;
    rewards_btc: number;
    gifts_btc: number;
    rebates_btc: number;

    year_to_date_capital_gains: number;
  }

  // The live price
  interface LiveBtcPriceResponse {
    USD: number;
    /** Where it came from: "mempool", or a public site ("kraken", "bitstamp"). */
    source?: string;
    /** When it arrived (UTC, "…Z"). */
    at?: string;
  }

  // Transactions
  /** A transaction as the API sends it (amounts as strings). */
  interface ITransactionRaw {
    id: number;
    from_account_id: number | null;
    to_account_id: number | null;
    type: TransactionType;
    amount?: string | number;
    fee_amount?: string | number;
    cost_basis_usd?: string | number;
    proceeds_usd?: string | number;
    fmv_usd?: string | number;
    realized_gain_usd?: string | number;
    timestamp: string;
    holding_period?: string | null;
    external_ref?: string | null;
    source?: string | null;
    purpose?: string | null;
    fee_currency?: string;
    created_at?: string;
    updated_at?: string;

    // The proceeds as typed; proceeds_usd is net of fees
    gross_proceeds_usd?: string | number;
    broker_reporting?: BrokerReporting | null;
    fee_usd?: string | number | null; // a BTC fee's stored USD value
    fee_usd_manual?: boolean;         // typed by the user
    acquired_at?: string | null;      // a My BTC / Gift deposit's date originally acquired, YYYY-MM-DD
    price_moment?: PriceMoment | null; // its priced values': the hour's price or the day's
    cost_basis_from_price?: boolean;  // an income or rebate value BitcoinTX filled in
    proceeds_from_price?: boolean;    // a Spent's proceeds BitcoinTX filled in
    fmv_from_price?: boolean;         // a gift's, donation's or lost coins' value BitcoinTX filled in (#255)
    price_used?: PriceUsed | null;    // the stored price they came from (#145)
  }

  /** The stored price a transaction's filled-in values came from (#145). */
  interface PriceUsed {
    at: string; // the hour's or the day's start, UTC
    moment: PriceMoment;
    source: string; // "bitstamp", "mempool", "kraken"…
    usd_per_btc: string | number;
  }

  /** A transaction with its amounts as numbers (parseTransaction). */
  interface ITransaction {
    id: number;
    from_account_id: number | null;
    to_account_id: number | null;
    type: TransactionType;
    amount: number;
    fee_amount: number;
    cost_basis_usd: number;
    proceeds_usd: number;
    fmv_usd?: number;
    realized_gain_usd: number;
    timestamp: string;   // ISO8601
    holding_period?: string;
    external_ref?: string;
    source?: string;
    purpose?: string;
    fee_currency?: string;
    created_at?: string;
    updated_at?: string;

    gross_proceeds_usd?: number;
    broker_reporting?: BrokerReporting | null;
    fee_usd?: number | null;
    fee_usd_manual?: boolean;
    acquired_at?: string | null;
    price_moment?: PriceMoment | null;
    cost_basis_from_price?: boolean;
    proceeds_from_price?: boolean;
    fmv_from_price?: boolean;
    price_used?: PriceUsed | null;
  }

  /** The moment a value BitcoinTX priced came from: the price when its hour
   * began (UTC), or that day's 00:00 UTC price where there was no hourly one. */
  type PriceMoment = "hour" | "day";

  type SortMode = "TIMESTAMP_DESC" | "CREATION_DESC";

  interface IAccountMapping {
    from_account_id: number;
    to_account_id: number;
  }

  /** The body of POST and PUT /api/transactions. */
  interface ICreateTransactionPayload {
    from_account_id: number;
    to_account_id: number;
    type: TransactionType;
    amount: number;
    timestamp: string;    // ISO8601
    fee_amount: number;
    fee_currency: Currency;
    cost_basis_usd: number | null; // null = not given (server fills an income basis)
    proceeds_usd?: number | null;  // null = not given (Spent: that hour's value)
    fmv_usd?: number | null;
    source?: string;
    purpose?: string;

    gross_proceeds_usd?: number;
    broker_reporting?: BrokerReporting | null;
    // A BTC fee's USD value: a number is kept as typed; null = go back to the
    // price (the hour's); left out = keep what's stored (or price a new fee).
    fee_usd?: number | null;
    // A My BTC / Gift deposit's date originally acquired (ISO 8601); null = the deposit's date
    acquired_at?: string | null;
  }

  interface ApiErrorResponse {
    detail?: string;
    errors?: Record<string, string[]>;
  }

  // The transaction form
  type TransactionType = "Deposit" | "Withdrawal" | "Transfer" | "Buy" | "Sell";

  type AccountType = "Bank" | "Wallet" | "Exchange" | "External";

  type DepositSource = "N/A" | "MyBTC" | "Gift" | "Inherited" | "Income" | "Interest" | "Reward" | "Rebate";
  type WithdrawalPurpose = "N/A" | "Spent" | "Gift" | "Donation" | "Lost";
  // What a broker reported on Form 1099-DA/1099-B (backend.constants.BROKER_REPORTING_VALUES)
  type BrokerReporting = "none" | "proceeds" | "basis";
  type Currency = "USD" | "BTC";

  /** A BTC field's value: a number, or its plain digits ("0.00000005") where
   * JavaScript would write the number in exponent form (#101, btcText). The
   * field reads it back as a number (valueAsNumber). */
  type BtcFieldValue = number | string;

  interface TransactionFormData {
    type: TransactionType;
    timestamp: string;

    // Single-account
    account?: AccountType;
    currency?: Currency;
    amount?: BtcFieldValue;
    source?: DepositSource;      // for BTC deposit
    purpose?: WithdrawalPurpose; // for BTC withdrawal
    fee?: BtcFieldValue;
    costBasisUSD?: number;
    proceeds_usd?: number;
    fmv_usd?: number;

    // Transfer
    fromAccount?: AccountType;
    fromCurrency?: Currency;
    toAccount?: AccountType;
    toCurrency?: Currency;
    amountFrom?: BtcFieldValue;
    amountTo?: BtcFieldValue;

    // Buy / Sell
    amountUSD?: number;
    amountBTC?: BtcFieldValue;

    // For Buy transactions: source account (Bank or Exchange)
    buyFromAccount?: "Bank" | "Exchange";

    // A Sell's proceeds as typed, before fees
    grossProceedsUSD?: number;
    // Form 1099-DA override; "" = automatic
    brokerReporting?: BrokerReporting | "";
    // A BTC fee's USD value, typed by the user; blank = that hour's price
    feeUSD?: number;
    feeUSDManual?: boolean; // the stored value was typed (clearing it sends null)
    feeUSDStored?: number;  // the stored value, shown as a hint
    priceMoment?: PriceMoment | null; // the stored priced values' moment
    // Where the saved values came from (#145): undefined for a new transaction
    costBasisFromPrice?: boolean;
    proceedsFromPrice?: boolean;
    fmvFromPrice?: boolean;
    costBasisStored?: number;
    proceedsStored?: number;
    fmvStored?: number;
    priceUsed?: PriceUsed | null;
    // A My BTC / Gift deposit's date originally acquired ("2021-03-14"); blank = the deposit's date.
    // An Inherited deposit's date of death (required)
    acquiredDate?: string;
  }

  // A Settings section's share of the page's state: one action at a time
  // (every button waits while one runs) and one message line.
  interface SettingsSectionProps {
    loading: boolean;
    setLoading: (loading: boolean) => void;
    setMessage: (message: string) => void;
  }

  interface TransactionFormProps {
    id?: string;
    onDirtyChange?: (dirty: boolean) => void;
    onSubmitSuccess?: () => void;

    // Editing a saved transaction
    transactionId?: number | null;
    onUpdateStatusChange?: (updating: boolean) => void;
  }

  // The calculator's pending operation
  type Operation = "+" | "-" | "*" | "/" | null;
}

export {}; // A module, so that `declare global` applies
