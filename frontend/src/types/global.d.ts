/* FILE: frontend/src/types/global.d.ts */

declare global {
  // --------------------------------------------------------------
  // 0) PyWebView Desktop API Types
  // --------------------------------------------------------------

  /**
   * Response from pywebview save_file API
   */
  interface PyWebViewSaveResult {
    success: boolean;
    path?: string;
    error?: string;
  }

  /**
   * PyWebView JavaScript API exposed by the desktop app
   */
  interface PyWebViewAPI {
    /**
     * Save a file using native macOS save dialog
     * @param filename - Suggested filename
     * @param data_base64 - Base64-encoded file content
     * @param file_type - File type hint (pdf, csv)
     */
    save_file(
      filename: string,
      data_base64: string,
      file_type: string
    ): Promise<PyWebViewSaveResult>;

    /**
     * Check if running in desktop mode
     */
    is_desktop(): Promise<boolean>;
  }

  /**
   * Extended Window interface with pywebview API
   */
  interface Window {
    pywebview?: {
      api: PyWebViewAPI;
    };
  }

  // --------------------------------------------------------------
  // 1) Domain Models for Account Balances & Gains/Losses
  // --------------------------------------------------------------

  interface AccountBalance {
    account_id: number;
    name: string;
    currency: string;
    balance: number | string; // parseDecimal
  }

  interface AverageCostBasis {
    averageCostBasis: number; 
  }

  interface GainsAndLossesRaw {
    // -- Legacy fields
    sells_proceeds?: string | number;
    withdrawals_spent?: string | number;
    income_earned?: string | number;
    interest_earned?: string | number;
    rewards_earned?: string | number;
    gifts_received?: string | number;
    realized_gains?: string | number;
    total_income?: string | number;
    fees?: {
      USD?: string | number;
      BTC?: string | number;
    };
    total_gains?: string | number;
    total_losses?: string | number;

    // -- Old short/long fields (back compat)
    short_term_realized_gains?: string | number;
    long_term_realized_gains?: string | number;
    total_realized_gains_usd?: string | number;

    // -- New detailed short/long fields
    short_term_gains?: string | number;
    short_term_losses?: string | number;
    short_term_net?: string | number;
    long_term_gains?: string | number;
    long_term_losses?: string | number;
    long_term_net?: string | number;
    total_net_capital_gains?: string | number;

    // -- New BTC fields (Income, Interest, Rewards, Gifts)
    income_btc?: string | number;
    interest_btc?: string | number;
    rewards_btc?: string | number;
    gifts_btc?: string | number;

    // -- ADDED: Year to Date Gains
    year_to_date_capital_gains?: string | number; // <-- ADDED
  }

  interface GainsAndLosses {
    // -- Legacy fields
    sells_proceeds: number;
    withdrawals_spent: number;
    income_earned: number;
    interest_earned: number;
    rewards_earned: number;
    gifts_received: number;
    realized_gains: number;
    total_income: number;
    fees: {
      USD: number;
      BTC: number;
    };
    total_gains: number;
    total_losses: number;

    // -- Old short/long fields (back compat)
    short_term_realized_gains?: number;
    long_term_realized_gains?: number;
    total_realized_gains_usd?: number;

    // -- New detailed short/long fields
    short_term_gains: number;
    short_term_losses: number;
    short_term_net: number;
    long_term_gains: number;
    long_term_losses: number;
    long_term_net: number;
    total_net_capital_gains: number;

    // -- New BTC fields (Income, Interest, Rewards, Gifts)
    income_btc: number;
    interest_btc: number;
    rewards_btc: number;
    gifts_btc: number;

    // -- ADDED: Year to Date Gains
    year_to_date_capital_gains: number; // <-- ADDED
  }

  // --------------------------------------------------------------
  // 1a) Optional: Bitcoin Price API Types
  // --------------------------------------------------------------

  interface LiveBtcPriceResponse {
    USD: number; // e.g. { USD: 12345.67 }
  }

  interface BtcPriceHistoryPoint {
    time: number;  // e.g. Unix timestamp
    price: number; // in USD
  }

  // --------------------------------------------------------------
  // 2) Domain Models for Transactions
  // --------------------------------------------------------------

  /**
   * Raw transaction data from the backend (strings for amounts).
   */
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

    // NEW: For Sell transactions, store gross proceeds typed by the user
    gross_proceeds_usd?: string | number; // <-- ADDED
    broker_reporting?: BrokerReporting | null;
  }

  /**
   * Parsed transaction data (numbers for amounts).
   */
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

    // NEW: For Sell transactions, store gross proceeds typed by the user
    gross_proceeds_usd?: number; // <-- ADDED
    broker_reporting?: BrokerReporting | null;
  }

  type SortMode = "TIMESTAMP_DESC" | "CREATION_DESC";

  interface IAccountMapping {
    from_account_id: number;
    to_account_id: number;
  }

  /**
   * Payload for creating (POST) a transaction (double-entry).
   */
  interface ICreateTransactionPayload {
    from_account_id: number;
    to_account_id: number;
    type: TransactionType;
    amount: number;
    timestamp: string;    // ISO8601
    fee_amount: number;
    fee_currency: Currency;
    cost_basis_usd: number;
    proceeds_usd?: number; // optional for certain types
    fmv_usd?: number;
    source?: string;
    purpose?: string;
    is_locked: boolean;   // only on creation

    // NEW: For Sell transactions
    gross_proceeds_usd?: number; // <-- ADDED
    broker_reporting?: BrokerReporting | null;
  }

  /**
   * If you want a separate shape for updating (PUT),
   * same as create but typically no is_locked.
   */
  type IUpdateTransactionPayload = Omit<ICreateTransactionPayload, "is_locked">;

  interface ApiErrorResponse {
    detail?: string;
    errors?: Record<string, string[]>;
  }

  // --------------------------------------------------------------
  // 3) Types for the TransactionForm
  // --------------------------------------------------------------

  type TransactionType = "Deposit" | "Withdrawal" | "Transfer" | "Buy" | "Sell";

  /**
   * Include External if your code uses it
   */
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

    // NEW: For Sell transactions, the user's typed gross proceeds
    grossProceedsUSD?: number; // <-- ADDED
    // Form 1099-DA override; "" = automatic
    brokerReporting?: BrokerReporting | "";
  }

  // Optional global props for TransactionForm if you want them globally
  interface TransactionFormProps {
    id?: string;
    onDirtyChange?: (dirty: boolean) => void;
    onSubmitSuccess?: () => void;

    // For editing existing transaction
    transactionId?: number | null;
    onUpdateStatusChange?: (updating: boolean) => void;
  }

  // --------------------------------------------------------------
  // 4) Calculator (if you have one)
  // --------------------------------------------------------------
  type Operation = "+" | "-" | "*" | "/" | null;
}

export {}; // Ensures this file is treated as a module.
