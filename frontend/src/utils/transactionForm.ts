// FILE: frontend/src/utils/transactionForm.ts
//
// Pure mapping between the transaction form and the API, kept out of the
// component so it can be unit-tested (src/utils/transactionForm.test.ts).
import { parseDecimal } from "./format";

/**
 * localDatetimeToIso:
 * Converts "datetime-local" (e.g. "2025-03-01T12:00")
 * to a full ISO8601 string for the backend.
 */
export function localDatetimeToIso(localDatetime: string): string {
  return new Date(localDatetime).toISOString();
}

// Hardcoded account IDs
const BANK_ID = 1;
const EXTERNAL_ID = 99;
const EXCHANGE_USD_ID = 3;
const EXCHANGE_BTC_ID = 4;

/**
 * mapAccountToId:
 * Convert an AccountType + Currency to the numeric ID recognized by the backend.
 */
export function mapAccountToId(account?: AccountType, currency?: Currency): number {
  if (account === "Bank") return 1;
  if (account === "Wallet") return 2;
  if (account === "Exchange") {
    return currency === "BTC" ? EXCHANGE_BTC_ID : EXCHANGE_USD_ID;
  }
  return 0;
}

/**
 * mapDoubleEntryAccounts:
 * Single-entry style => from/to IDs for the ledger.
 */
export function mapDoubleEntryAccounts(data: TransactionFormData): IAccountMapping {
  switch (data.type) {
    case "Deposit":
      return {
        from_account_id: EXTERNAL_ID,
        to_account_id: mapAccountToId(data.account, data.currency),
      };
    case "Withdrawal":
      return {
        from_account_id: mapAccountToId(data.account, data.currency),
        to_account_id: EXTERNAL_ID,
      };
    case "Transfer":
      return {
        from_account_id: mapAccountToId(data.fromAccount, data.fromCurrency),
        to_account_id: mapAccountToId(data.toAccount, data.toCurrency),
      };
    case "Buy":
      return {
        from_account_id: data.buyFromAccount === "Bank" ? BANK_ID : EXCHANGE_USD_ID,
        to_account_id: EXCHANGE_BTC_ID,
      };
    case "Sell":
      return {
        from_account_id: EXCHANGE_BTC_ID,
        to_account_id: EXCHANGE_USD_ID,
      };
    default:
      return { from_account_id: 0, to_account_id: 0 };
  }
}

/**
 * mapTransactionToFormData:
 * Converts an ITransaction (fetched from backend) into TransactionFormData
 * so we can populate the form fields in edit mode.
 *
 * // NEW: GROSS PROCEEDS FOR SELL
 * We read tx.gross_proceeds_usd (if present) into 'grossProceedsUSD' for the user to see.
 */
export function mapTransactionToFormData(tx: ITransaction): TransactionFormData {
  // Common fields
  const baseData: TransactionFormData = {
    type: tx.type,
    timestamp: new Date(tx.timestamp).toISOString().slice(0, 16), // for datetime-local
    fee: tx.fee_amount ?? 0,
    costBasisUSD: tx.cost_basis_usd ?? 0,
    proceeds_usd: tx.proceeds_usd ?? 0,
    fmv_usd: tx.fmv_usd ?? 0,

    // NEW: GROSS PROCEEDS FOR SELL
    grossProceedsUSD: tx.gross_proceeds_usd ?? 0,
    brokerReporting: tx.broker_reporting ?? "",
  };

  // Helper to convert account_id => "Bank", "Wallet", "Exchange", etc.
  const accountIdToType = (id: number): AccountType => {
    switch (id) {
      case 1:
        return "Bank";
      case 2:
        return "Wallet";
      case 3:
      case 4:
        return "Exchange";
      default:
        return "External";
    }
  };

  // Helper to guess currency from ID
  const getCurrencyFromAccountId = (id: number): Currency =>
    id === 1 || id === 3 ? "USD" : "BTC";

  switch (tx.type) {
    case "Deposit": {
      const toAcctId = tx.to_account_id ?? 0;
      return {
        ...baseData,
        account: accountIdToType(toAcctId),
        currency: getCurrencyFromAccountId(toAcctId),
        amount: tx.amount,
        source: (tx.source ?? "N/A") as DepositSource,
      };
    }
    case "Withdrawal": {
      const fromAcctId = tx.from_account_id ?? 0;
      return {
        ...baseData,
        account: accountIdToType(fromAcctId),
        currency: getCurrencyFromAccountId(fromAcctId),
        amount: tx.amount,
        purpose: (tx.purpose ?? "N/A") as WithdrawalPurpose,
        // Stored proceeds_usd is net of the BTC fee; edit the user's gross
        proceeds_usd: tx.gross_proceeds_usd ?? tx.proceeds_usd ?? 0,
      };
    }
    case "Transfer": {
      const fromAcctId = tx.from_account_id ?? 0;
      const toAcctId = tx.to_account_id ?? 0;
      const fromAccount = accountIdToType(fromAcctId);
      const toAccount = accountIdToType(toAcctId);
      const fromCurrency = getCurrencyFromAccountId(fromAcctId);
      const toCurrency = getCurrencyFromAccountId(toAcctId);

      return {
        ...baseData,
        fromAccount,
        toAccount,
        fromCurrency,
        toCurrency,
        amountFrom: tx.amount,
        // If it was BTC with a fee, "amountTo" is (amount - fee).
        amountTo:
          tx.type === "Transfer" && fromCurrency === "BTC"
            ? tx.amount - (tx.fee_amount ?? 0)
            : tx.amount,
      };
    }
    case "Buy": {
      // Determine if Buy was from Bank (ID 1) or Exchange USD (ID 3)
      const buyFromAccount = tx.from_account_id === 1 ? "Bank" : "Exchange";
      return {
        ...baseData,
        account: "Exchange",
        buyFromAccount,
        amountUSD: tx.cost_basis_usd ?? 0,
        amountBTC: tx.amount,
      };
    }
    case "Sell":
      return {
        ...baseData,
        account: "Exchange",
        amountBTC: tx.amount,

        // OLD: form used "amountUSD" for net proceeds
        // NEW: we treat "amountUSD" as "grossProceedsUSD" for user input
        grossProceedsUSD: tx.gross_proceeds_usd ?? tx.proceeds_usd ?? 0,
      };
    default:
      // Return the base for safety
      return baseData;
  }
}

/**
 * buildTransactionPayload:
 * Form values => the body for POST/PUT /api/transactions.
 */
export function buildTransactionPayload(
  data: TransactionFormData,
): Omit<ICreateTransactionPayload, "is_locked"> {
  data = { ...data }; // never modify the caller's form values

  // 1) If BTC withdrawal & user didn't provide proceeds, default to 0
  if (
    data.type === "Withdrawal" &&
    data.currency === "BTC" &&
    !data.proceeds_usd
  ) {
    data.proceeds_usd = 0;
  }

  // 2) from/to IDs
  const { from_account_id, to_account_id } = mapDoubleEntryAccounts(data);

  // 3) Convert datetime => ISO
  const isoTimestamp = localDatetimeToIso(data.timestamp);

  // 4) Prepare fields for the payload
  let amount = 0;
  let feeCurrency: Currency = "USD";
  let source: string | undefined;
  let purpose: string | undefined;
  let cost_basis_usd = 0;
  let proceeds_usd: number | undefined;
  let fmv_usd: number | undefined;
  let gross_proceeds_usd: number | undefined; // <-- new

  switch (data.type) {
    case "Deposit":
      amount = parseDecimal(data.amount);
      feeCurrency = data.currency === "BTC" ? "BTC" : "USD";
      source = data.source && data.source !== "N/A" ? data.source : "N/A";
      if (
        data.currency === "BTC" &&
        (data.account === "Wallet" || data.account === "Exchange")
      ) {
        cost_basis_usd = parseDecimal(data.costBasisUSD);
      }
      break;

    case "Withdrawal":
      amount = parseDecimal(data.amount);
      feeCurrency = data.currency === "BTC" ? "BTC" : "USD";
      purpose = data.purpose && data.purpose !== "N/A" ? data.purpose : "N/A";
      proceeds_usd = parseDecimal(data.proceeds_usd);
      fmv_usd = parseDecimal(data.fmv_usd);
      break;

    case "Transfer":
      amount = parseDecimal(data.amountFrom);
      feeCurrency = data.fromCurrency === "BTC" ? "BTC" : "USD";
      break;

    case "Buy":
      amount = parseDecimal(data.amountBTC);
      feeCurrency = "USD";
      cost_basis_usd = parseDecimal(data.amountUSD);
      break;

    case "Sell":
      // NEW: we interpret "amountBTC" as the BTC being sold
      amount = parseDecimal(data.amountBTC);
      feeCurrency = "USD";

      // Instead of storing net proceeds in "proceeds_usd," we store user input as "gross_proceeds_usd"
      gross_proceeds_usd = parseDecimal(data.grossProceedsUSD);
      break;
  }

  // Form 1099-DA override: only sales and BTC spends reach a broker form
  const brokerApplies =
    data.type === "Sell" ||
    (data.type === "Withdrawal" && data.currency === "BTC" && data.purpose === "Spent");
  const broker_reporting =
    brokerApplies && data.brokerReporting ? data.brokerReporting : null;

  // 5) Build payload
  return {
    type: data.type,
    timestamp: isoTimestamp,
    from_account_id,
    to_account_id,
    amount,
    fee_amount: parseDecimal(data.fee),
    fee_currency: feeCurrency,
    cost_basis_usd,
    proceeds_usd,   // might be undefined if Sell
    gross_proceeds_usd, // <-- new field for Sell
    fmv_usd,
    source,
    purpose,
    broker_reporting,
  };
}
