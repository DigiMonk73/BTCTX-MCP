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

    // The BTC received as income, interest, rewards and gifts
    income_btc?: string | number;
    interest_btc?: string | number;
    rewards_btc?: string | number;
    gifts_btc?: string | number;

    year_to_date_capital_gains?: string | number;
  }

  interface GainsAndLosses {
    sells_proceeds: number;
    withdrawals_spent: number;
    income_earned: number;
    interest_earned: number;
    rewards_earned: number;
    gifts_received: number;
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

    year_to_date_capital_gains: number;
  }

  // The live price
  interface LiveBtcPriceResponse {
    USD: number;
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
    is_locked: boolean;
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
    is_locked: boolean;
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
  }

  type SortMode = "TIMESTAMP_DESC" | "CREATION_DESC";

  interface IAccountMapping {
    from_account_id: number;
    to_account_id: number;
  }

  /** The body of POST /api/transactions (PUT sends the same without is_locked). */
  interface ICreateTransactionPayload {
    from_account_id: number;
    to_account_id: number;
    type: TransactionType;
    amount: number;
    timestamp: string;    // ISO8601
    fee_amount: number;
    fee_currency: Currency;
    cost_basis_usd: number | null; // null = not given (server fills an income basis)
    proceeds_usd?: number | null;  // null = not given (Spent: that day's value)
    fmv_usd?: number | null;
    source?: string;
    purpose?: string;
    is_locked: boolean;   // only on creation

    gross_proceeds_usd?: number;
    broker_reporting?: BrokerReporting | null;
    // A BTC fee's USD value: a number is kept as typed; null = go back to the
    // day's price; left out = keep what's stored (or price a new fee).
    fee_usd?: number | null;
  }

  interface ApiErrorResponse {
    detail?: string;
    errors?: Record<string, string[]>;
  }

  // The transaction form
  type TransactionType = "Deposit" | "Withdrawal" | "Transfer" | "Buy" | "Sell";

  type AccountType = "Bank" | "Wallet" | "Exchange" | "External";

  type DepositSource = "N/A" | "MyBTC" | "Gift" | "Income" | "Interest" | "Reward";
  type WithdrawalPurpose = "N/A" | "Spent" | "Gift" | "Donation" | "Lost";
  // What a broker reported on Form 1099-DA/1099-B (backend.constants.BROKER_REPORTING_VALUES)
  type BrokerReporting = "none" | "proceeds" | "basis";
  type Currency = "USD" | "BTC";

  interface TransactionFormData {
    type: TransactionType;
    timestamp: string;

    // Single-account
    account?: AccountType;
    currency?: Currency;
    amount?: number;
    source?: DepositSource;      // for BTC deposit
    purpose?: WithdrawalPurpose; // for BTC withdrawal
    fee?: number;
    costBasisUSD?: number;
    proceeds_usd?: number;
    fmv_usd?: number;

    // Transfer
    fromAccount?: AccountType;
    fromCurrency?: Currency;
    toAccount?: AccountType;
    toCurrency?: Currency;
    amountFrom?: number;
    amountTo?: number;

    // Buy / Sell
    amountUSD?: number;
    amountBTC?: number;

    // For Buy transactions: source account (Bank or Exchange)
    buyFromAccount?: "Bank" | "Exchange";

    // A Sell's proceeds as typed, before fees
    grossProceedsUSD?: number;
    // Form 1099-DA override; "" = automatic
    brokerReporting?: BrokerReporting | "";
    // A BTC fee's USD value, typed by the user; blank = that day's price
    feeUSD?: number;
    feeUSDManual?: boolean; // the stored value was typed (clearing it sends null)
    feeUSDStored?: number;  // the stored value, shown as a hint
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
