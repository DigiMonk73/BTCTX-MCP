// Pure mapping between the transaction form and the API, kept out of the
// component so it can be unit-tested (src/utils/transactionForm.test.ts).
import { optionalDecimal, parseDecimal } from "./format";

/** A "datetime-local" value ("2025-03-01T12:00", local time) as ISO 8601 UTC. */
export function localDatetimeToIso(localDatetime: string): string {
  return new Date(localDatetime).toISOString();
}

/**
 * The inverse of localDatetimeToIso: a moment as this computer's wall-clock
 * time for a "datetime-local" input (e.g. "2026-07-31T15:16:07"), seconds
 * included. Not toISOString(), which gives UTC wall time: the input would
 * show it as local time and every save would shift it by the UTC offset.
 */
export function toDatetimeLocal(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
  );
}

// The server's fixed account ids
const BANK_ID = 1;
const EXTERNAL_ID = 99;
const EXCHANGE_USD_ID = 3;
const EXCHANGE_BTC_ID = 4;

/** The account id for a form's account and currency (0: none chosen). */
export function mapAccountToId(account?: AccountType, currency?: Currency): number {
  if (account === "Bank") return 1;
  if (account === "Wallet") return 2;
  if (account === "Exchange") {
    return currency === "BTC" ? EXCHANGE_BTC_ID : EXCHANGE_USD_ID;
  }
  return 0;
}

/** The ledger's from and to accounts for what the form shows as one account. */
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

function accountIdToType(id: number): AccountType {
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
}

function accountCurrency(id: number): Currency {
  return id === 1 || id === 3 ? "USD" : "BTC";
}

/** The fields every type's form shows. */
function commonFormData(tx: ITransaction): TransactionFormData {
  return {
    type: tx.type,
    timestamp: toDatetimeLocal(new Date(tx.timestamp)),
    fee: tx.fee_amount ?? 0,
    costBasisUSD: tx.cost_basis_usd ?? 0,
    proceeds_usd: tx.proceeds_usd ?? 0,
    fmv_usd: tx.fmv_usd ?? 0,
    grossProceedsUSD: tx.gross_proceeds_usd ?? 0,
    brokerReporting: tx.broker_reporting ?? "",
    feeUSD: tx.fee_usd_manual && tx.fee_usd != null ? tx.fee_usd : undefined,
    feeUSDManual: tx.fee_usd_manual ?? false,
    feeUSDStored: tx.fee_usd ?? undefined,
  };
}

/** Each type's own form fields, read back from a saved transaction. */
const TYPE_FORM_DATA: Record<TransactionType, (tx: ITransaction) => Partial<TransactionFormData>> = {
  Deposit: (tx) => {
    const accountId = tx.to_account_id ?? 0;
    return {
      account: accountIdToType(accountId),
      currency: accountCurrency(accountId),
      amount: tx.amount,
      source: (tx.source ?? "N/A") as DepositSource,
    };
  },
  Withdrawal: (tx) => {
    const accountId = tx.from_account_id ?? 0;
    return {
      account: accountIdToType(accountId),
      currency: accountCurrency(accountId),
      amount: tx.amount,
      purpose: (tx.purpose ?? "N/A") as WithdrawalPurpose,
      // Stored proceeds_usd is net of the BTC fee; edit the user's gross
      proceeds_usd: tx.gross_proceeds_usd ?? tx.proceeds_usd ?? 0,
    };
  },
  Transfer: (tx) => {
    const fromId = tx.from_account_id ?? 0;
    const toId = tx.to_account_id ?? 0;
    const fromCurrency = accountCurrency(fromId);
    return {
      fromAccount: accountIdToType(fromId),
      toAccount: accountIdToType(toId),
      fromCurrency,
      toCurrency: accountCurrency(toId),
      amountFrom: tx.amount,
      // A BTC transfer's fee comes out of the amount: what arrived is the rest
      amountTo: fromCurrency === "BTC" ? tx.amount - (tx.fee_amount ?? 0) : tx.amount,
    };
  },
  Buy: (tx) => ({
    account: "Exchange",
    buyFromAccount: tx.from_account_id === 1 ? "Bank" : "Exchange",
    amountUSD: tx.cost_basis_usd ?? 0,
    amountBTC: tx.amount,
  }),
  Sell: (tx) => ({
    account: "Exchange",
    amountBTC: tx.amount,
    // The user's figure: stored proceeds_usd is net of the fee
    grossProceedsUSD: tx.gross_proceeds_usd ?? tx.proceeds_usd ?? 0,
  }),
};

/** A saved transaction as the form shows it for editing. */
export function mapTransactionToFormData(tx: ITransaction): TransactionFormData {
  const typeFormData = TYPE_FORM_DATA[tx.type];
  return typeFormData ? { ...commonFormData(tx), ...typeFormData(tx) } : commonFormData(tx);
}

/** What the payload says depends on the transaction's type. */
interface TypePayload {
  amount: number;
  feeCurrency: Currency;
  source?: string;
  purpose?: string;
  // null = not given: the server fills what it can (an income deposit's
  // basis, a Spent withdrawal's proceeds, a gift's FMV) from that day's price.
  cost_basis_usd: number | null;
  proceeds_usd?: number | null;
  fmv_usd?: number | null;
  gross_proceeds_usd?: number;
}

const TYPE_PAYLOAD: Record<TransactionType, (data: TransactionFormData) => TypePayload> = {
  Deposit: (data) => ({
    amount: parseDecimal(data.amount),
    feeCurrency: data.currency === "BTC" ? "BTC" : "USD",
    source: data.source && data.source !== "N/A" ? data.source : "N/A",
    // Only BTC received has a basis
    cost_basis_usd:
      data.currency === "BTC" && (data.account === "Wallet" || data.account === "Exchange")
        ? optionalDecimal(data.costBasisUSD)
        : null,
  }),
  Withdrawal: (data) => ({
    amount: parseDecimal(data.amount),
    feeCurrency: data.currency === "BTC" ? "BTC" : "USD",
    purpose: data.purpose && data.purpose !== "N/A" ? data.purpose : "N/A",
    cost_basis_usd: null,
    proceeds_usd: optionalDecimal(data.proceeds_usd),
    fmv_usd: optionalDecimal(data.fmv_usd),
  }),
  Transfer: (data) => ({
    amount: parseDecimal(data.amountFrom),
    feeCurrency: data.fromCurrency === "BTC" ? "BTC" : "USD",
    cost_basis_usd: null,
  }),
  Buy: (data) => ({
    amount: parseDecimal(data.amountBTC),
    feeCurrency: "USD",
    cost_basis_usd: parseDecimal(data.amountUSD),
  }),
  Sell: (data) => ({
    amount: parseDecimal(data.amountBTC),
    feeCurrency: "USD",
    cost_basis_usd: null,
    // The user's figure; the server works out the net proceeds
    gross_proceeds_usd: parseDecimal(data.grossProceedsUSD),
  }),
};

/** The Form 1099-DA override: only sales and BTC spends reach a broker form. */
function brokerReporting(data: TransactionFormData): BrokerReporting | null {
  const brokerApplies =
    data.type === "Sell" ||
    (data.type === "Withdrawal" && data.currency === "BTC" && data.purpose === "Spent");
  return brokerApplies && data.brokerReporting ? data.brokerReporting : null;
}

/**
 * A BTC fee's USD value (transfers and BTC withdrawals): typed -> kept;
 * cleared after being typed -> null (back to the day's price); otherwise
 * undefined, left out, so a stored value is kept and a new fee is priced by
 * the server.
 */
function feeUsd(data: TransactionFormData, feeCurrency: Currency): number | null | undefined {
  if (feeCurrency === "BTC" && (data.type === "Transfer" || data.type === "Withdrawal")) {
    const typed = optionalDecimal(data.feeUSD);
    return typed ?? (data.feeUSDManual ? null : undefined);
  }
  return undefined;
}

/** Form values => the body for POST/PUT /api/transactions. */
export function buildTransactionPayload(
  data: TransactionFormData,
): Omit<ICreateTransactionPayload, "is_locked"> {
  const { from_account_id, to_account_id } = mapDoubleEntryAccounts(data);
  const typePayload = TYPE_PAYLOAD[data.type];
  const values: TypePayload = typePayload ? typePayload(data) : { amount: 0, feeCurrency: "USD", cost_basis_usd: null };
  const fee_usd = feeUsd(data, values.feeCurrency);
  return {
    type: data.type,
    timestamp: localDatetimeToIso(data.timestamp),
    from_account_id,
    to_account_id,
    amount: values.amount,
    fee_amount: parseDecimal(data.fee),
    fee_currency: values.feeCurrency,
    cost_basis_usd: values.cost_basis_usd,
    proceeds_usd: values.proceeds_usd,
    gross_proceeds_usd: values.gross_proceeds_usd,
    fmv_usd: values.fmv_usd,
    source: values.source,
    purpose: values.purpose,
    broker_reporting: brokerReporting(data),
    ...(fee_usd !== undefined ? { fee_usd } : {}),
  };
}
