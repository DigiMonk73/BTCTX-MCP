// Pure mapping between the transaction form and the API, kept out of the
// component so it can be unit-tested (src/utils/transactionForm.test.ts).
// Accounts go by id, each one's currency read from the book (2.0 spec 5.13).
import { EXTERNAL_ID, accountCurrency, isBtcAccount, usdOf } from "./accounts";
import { btcText, optionalDecimal, parseDecimal } from "./format";
import { isBtcPurpose, isListedSource, isNotSold, listedPurpose, listedSource } from "./purposes";
import { dollarTransferFee, pastTheCent } from "./transferAmounts";
import { proceedsSent, withdrawalProceeds } from "./withdrawalProceeds";

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

/**
 * The ledger's from and to accounts. External's side and a Sell's dollars
 * follow from the type; every other id is sent as the form holds it, so a
 * row read back and saved unchanged keeps both (5.13). 0 = none chosen,
 * which the pickers' checks never let through.
 */
export function mapDoubleEntryAccounts(data: TransactionFormData, book: AccountBook): IAccountMapping {
  switch (data.type) {
    case "Deposit":
      return { from_account_id: EXTERNAL_ID, to_account_id: data.toAccountId ?? 0 };
    case "Withdrawal":
      return { from_account_id: data.fromAccountId ?? 0, to_account_id: EXTERNAL_ID };
    case "Sell":
      return { from_account_id: data.fromAccountId ?? 0, to_account_id: usdOf(book, data.fromAccountId) ?? 0 };
    default:
      return { from_account_id: data.fromAccountId ?? 0, to_account_id: data.toAccountId ?? 0 };
  }
}

/** The fields every type's form shows. */
function commonFormData(tx: ITransaction): TransactionFormData {
  return {
    type: tx.type,
    timestamp: toDatetimeLocal(new Date(tx.timestamp)),
    // Kept for every type (5.13); a null id is held as undefined
    fromAccountId: tx.from_account_id ?? undefined,
    toAccountId: tx.to_account_id ?? undefined,
    fee: tx.fee_amount ?? 0,
    costBasisUSD: tx.cost_basis_usd ?? 0,
    proceeds_usd: tx.proceeds_usd ?? 0,
    // Blank stays blank, so saving it fills it from the price (#255); a
    // sale's $0 (older forms saved one on every withdrawal) shows blank too,
    // so making it a gift fills it rather than sending $0 as the value
    fmv_usd: isNotSold(tx.purpose) ? tx.fmv_usd : tx.fmv_usd || undefined,
    grossProceedsUSD: tx.gross_proceeds_usd ?? 0,
    brokerReporting: tx.broker_reporting ?? "",
    feeUSD: tx.fee_usd_manual && tx.fee_usd != null ? tx.fee_usd : undefined,
    feeUSDManual: tx.fee_usd_manual ?? false,
    feeUSDStored: tx.fee_usd ?? undefined,
    priceMoment: tx.price_moment ?? null,
    ...valueOrigins(tx),
  };
}

/** Where the saved values came from, for the form's "From the price" / "Typed" (#145). */
function valueOrigins(tx: ITransaction): Partial<TransactionFormData> {
  return {
    costBasisFromPrice: tx.cost_basis_from_price ?? false,
    proceedsFromPrice: tx.proceeds_from_price ?? false,
    fmvFromPrice: tx.fmv_from_price ?? false,
    costBasisStored: tx.cost_basis_usd,
    proceedsStored: tx.gross_proceeds_usd ?? tx.proceeds_usd,
    fmvStored: tx.fmv_usd,
    priceUsed: tx.price_used ?? null,
  };
}

/** Each type's own form fields, read back from a saved transaction. */
const TYPE_FORM_DATA: Record<TransactionType, (tx: ITransaction, book: AccountBook) => Partial<TransactionFormData>> = {
  Deposit: (tx) => ({
    amount: tx.amount,
    source: listedSource(tx.source),
  }),
  Withdrawal: (tx, book) => {
    // A dollar withdrawal has none (#449)
    const proceeds = isBtcAccount(book, tx.from_account_id ?? undefined) ? withdrawalProceeds(tx) : undefined;
    return {
      amount: tx.amount,
      purpose: listedPurpose(tx.purpose),
      proceeds_usd: proceeds,
      proceedsStored: proceeds,
    };
  },
  Transfer: (tx, book) => {
    const fee = tx.fee_amount ?? 0;
    // A BTC transfer's amount is what left, its fee included: what arrived
    // is the rest, to the satoshi. A dollar transfer's is what arrived, its
    // fee on top (#447)
    if (transferCurrency(tx, book) === "BTC") {
      return { amountFrom: tx.amount, amountTo: Number((tx.amount - fee).toFixed(8)) };
    }
    // Dollars add up in cents (two amounts' float sum can carry a stray digit
    // past the cent); one stored past the cent keeps 8 places, for the form to say so
    const dollarPlaces = pastTheCent(tx.amount) || pastTheCent(fee) ? 8 : 2;
    return { amountFrom: Number((tx.amount + fee).toFixed(dollarPlaces)), amountTo: tx.amount };
  },
  Buy: (tx) => ({
    amountUSD: tx.cost_basis_usd ?? 0,
    amountBTC: tx.amount,
  }),
  Sell: (tx) => ({
    amountBTC: tx.amount,
    grossProceedsUSD: sellGross(tx),
  }),
};

/** A saved Transfer's currency: its From's, else its To's (one the book
 * lacks: a row saved before 0.9.2), else bitcoin, which every such row was. */
function transferCurrency(tx: ITransaction, book: AccountBook): Currency {
  return accountCurrency(book, tx.from_account_id ?? undefined) ??
    accountCurrency(book, tx.to_account_id ?? undefined) ?? "BTC";
}

/**
 * A Sell's gross proceeds, the user's figure (stored proceeds_usd is net of
 * the USD fee). A row saved before the gross was kept has none (parsed as 0):
 * its gross is the net plus that fee, as the server recovers it
 * (`_sell_net_proceeds`), so saving it unchanged takes no fee off again (#476).
 */
function sellGross(tx: ITransaction): number {
  if (tx.gross_proceeds_usd) return tx.gross_proceeds_usd;
  const net = tx.proceeds_usd ?? 0;
  if (net <= 0) return 0;
  // A Sell's fee is in dollars unless saved otherwise (the server's fee_currency_used)
  const usdFee = (tx.fee_currency || "USD").toUpperCase() === "USD" ? (tx.fee_amount ?? 0) : 0;
  return Number((net + usdFee).toFixed(2));
}

/** A saved transaction as the form shows it for editing; a date originally
 * acquired as the date stored, YYYY-MM-DD (#185: a date, which no timezone
 * moves; never read through a Date, which would). */
export function mapTransactionToFormData(tx: ITransaction, book: AccountBook): TransactionFormData {
  const typeFormData = TYPE_FORM_DATA[tx.type];
  const form = typeFormData ? { ...commonFormData(tx), ...typeFormData(tx, book) } : commonFormData(tx);
  if (tx.acquired_at) form.acquiredDate = tx.acquired_at;
  return form;
}

const BTC_FIELDS = ["amount", "fee", "amountFrom", "amountTo", "amountBTC"] as const;

/**
 * The form's BTC values that a field would show in exponent form (a 5-sat
 * amount as "5e-8"), as plain digits (#101). Set after the form is reset, so
 * its starting values stay numbers and nothing reads as changed.
 */
export function plainBtcText(form: TransactionFormData): Array<[(typeof BTC_FIELDS)[number], string]> {
  return BTC_FIELDS.flatMap((name) => {
    const value = form[name];
    return typeof value === "number" && String(value).includes("e") ? [[name, btcText(value)] as const] : [];
  });
}

/** What the payload says depends on the transaction's type. */
interface TypePayload {
  amount: number;
  feeCurrency: Currency;
  source?: string;
  purpose?: string;
  // null = not given: the server fills what it can (an income deposit's
  // basis, a Spent withdrawal's proceeds, a gift's FMV) from that hour's price.
  cost_basis_usd: number | null;
  proceeds_usd?: number | null;
  fmv_usd?: number | null;
  gross_proceeds_usd?: number;
  // A fee the type works out itself; else the Fee field's
  fee?: number;
}

type FormAccounts = Pick<TransactionFormData, "type" | "fromAccountId" | "toAccountId">;

/** Whether the account a Deposit goes into, or anything else leaves, holds bitcoin (5.1). */
export function inBtcAccount(data: FormAccounts, book: AccountBook): boolean {
  return isBtcAccount(book, data.type === "Deposit" ? data.toAccountId : data.fromAccountId);
}

/**
 * A withdrawal's purpose. A dollar one has no bitcoin purpose (Spent, Gift,
 * Donation, Lost): there it's one left from the hidden bitcoin fields
 * (#449). It may have a label of its own ("Rent", from an import), which an
 * edit sends back as it was.
 */
function withdrawalPurpose(data: TransactionFormData, book: AccountBook): string {
  const purpose = data.purpose && data.purpose !== "N/A" ? data.purpose : "N/A";
  return inBtcAccount(data, book) || !isBtcPurpose(purpose) ? purpose : "N/A";
}

/**
 * A deposit's source. A dollar one sends none of the listed ones: there
 * it's one left from the hidden bitcoin fields (#449). Text a version
 * before 1.1.0 saved goes back as it was, as the server keeps it.
 */
function depositSource(data: TransactionFormData, book: AccountBook): string {
  const source = data.source && data.source !== "N/A" ? data.source : "N/A";
  return inBtcAccount(data, book) || !isListedSource(source) ? source : "N/A";
}

// Only bitcoin received has a source and a basis, and only bitcoin leaving a
// purpose and a value: the form shows those fields for a bitcoin account
// alone, and one filled in before the account changed stays in the form
// though hidden, so a dollar deposit or withdrawal sends none (#449)
const TYPE_PAYLOAD: Record<TransactionType, (data: TransactionFormData, book: AccountBook) => TypePayload> = {
  Deposit: (data, book) => ({
    amount: parseDecimal(data.amount),
    feeCurrency: inBtcAccount(data, book) ? "BTC" : "USD",
    source: depositSource(data, book),
    cost_basis_usd: inBtcAccount(data, book) ? optionalDecimal(data.costBasisUSD) : null,
  }),
  Withdrawal: (data, book) => ({
    amount: parseDecimal(data.amount),
    feeCurrency: inBtcAccount(data, book) ? "BTC" : "USD",
    purpose: withdrawalPurpose(data, book),
    cost_basis_usd: null,
    proceeds_usd: inBtcAccount(data, book) ? proceedsSent(data) : null,
    fmv_usd: inBtcAccount(data, book) ? optionalDecimal(data.fmv_usd) : null,
  }),
  // A BTC transfer's amount is what left, its fee in it (filled in by
  // useFieldAutofill); a dollar transfer's is what arrived, the fee on top
  // (#447), as the server keeps both
  Transfer: (data, book) =>
    inBtcAccount(data, book)
      ? { amount: parseDecimal(data.amountFrom), feeCurrency: "BTC", cost_basis_usd: null }
      : {
          amount: parseDecimal(data.amountTo),
          feeCurrency: "USD",
          cost_basis_usd: null,
          fee: dollarTransferFee(parseDecimal(data.amountFrom), parseDecimal(data.amountTo)),
        },
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
function brokerReporting(data: TransactionFormData, book: AccountBook): BrokerReporting | null {
  const brokerApplies =
    data.type === "Sell" ||
    (data.type === "Withdrawal" && inBtcAccount(data, book) && data.purpose === "Spent");
  return brokerApplies && data.brokerReporting ? data.brokerReporting : null;
}

/** Deposit sources whose coins may have been acquired before the deposit
 * (an inheritance: on the date of death, #154). */
const ORIGINAL_DATE_SOURCES = ["MyBTC", "Gift", "Inherited"];

/** Whether a deposit takes "Date originally acquired" (an inheritance's
 * "Date of death"): My BTC, Gift or Inherited into a bitcoin account. */
export function takesOriginalDate(
  data: FormAccounts & Pick<TransactionFormData, "source">,
  book: AccountBook,
): boolean {
  return data.type === "Deposit" && inBtcAccount(data, book) && ORIGINAL_DATE_SOURCES.includes(data.source ?? "");
}

/** The date originally acquired, as a date alone (the server keeps it as
 * that date); null = none, so an edit to another source clears it. */
function acquiredAt(data: TransactionFormData, book: AccountBook): string | null {
  return takesOriginalDate(data, book) && data.acquiredDate ? data.acquiredDate : null;
}

/**
 * A BTC fee's USD value (transfers and BTC withdrawals): typed -> kept;
 * cleared after being typed -> null (back to the hour's price); otherwise
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
  book: AccountBook,
): ICreateTransactionPayload {
  const { from_account_id, to_account_id } = mapDoubleEntryAccounts(data, book);
  const typePayload = TYPE_PAYLOAD[data.type];
  const values: TypePayload = typePayload
    ? typePayload(data, book)
    : { amount: 0, feeCurrency: "USD", cost_basis_usd: null };
  const fee_usd = feeUsd(data, values.feeCurrency);
  return {
    type: data.type,
    timestamp: localDatetimeToIso(data.timestamp),
    from_account_id,
    to_account_id,
    amount: values.amount,
    fee_amount: values.fee ?? parseDecimal(data.fee),
    fee_currency: values.feeCurrency,
    cost_basis_usd: values.cost_basis_usd,
    proceeds_usd: values.proceeds_usd,
    gross_proceeds_usd: values.gross_proceeds_usd,
    fmv_usd: values.fmv_usd,
    source: values.source,
    purpose: values.purpose,
    broker_reporting: brokerReporting(data, book),
    acquired_at: acquiredAt(data, book),
    ...(fee_usd !== undefined ? { fee_usd } : {}),
  };
}
