// Which coins a Transfer moves, shown before it saves (#706): when to ask
// the server (POST /transactions/coins-moved, which runs the save's own
// path on a scratch copy of the ledger), with what, and the words around
// the list it gives. Asked with the body the Save sends, so once a transfer
// can name the coins it moves (#711), the list follows that choice.
import { accountName, chosenId, isBtcAccount } from "./accounts";
import { btcText, parseDecimal } from "./format";
import { buildTransactionPayload } from "./transactionForm";

/** A lot the save would put in the To account. */
export interface MovedCoin {
  acquired: string; // the date acquired, YYYY-MM-DD in the tax timezone
  btc: string;
  cost_usd: string;
  inherited: boolean;
}

/** The server's answer: coins and fee_btc are null when it couldn't work them out in time (detail says so). */
export interface CoinsMoved {
  coins: MovedCoin[] | null;
  fee_btc: string | null;
  detail: string | null;
}

type FormAccounts = Pick<TransactionFormData, "type" | "fromAccountId" | "toAccountId">;

/** A Transfer between two bitcoin accounts: the coins move with their dates
 * and cost. A move within one records only its fee (#159), and dollars
 * have no coins. */
export function movesCoins(values: FormAccounts, book: AccountBook): boolean {
  const fromId = chosenId(values.fromAccountId);
  const toId = chosenId(values.toAccountId);
  return values.type === "Transfer" && fromId !== undefined && toId !== undefined && fromId !== toId &&
    isBtcAccount(book, fromId) && isBtcAccount(book, toId);
}

/**
 * The body to ask with: the one the Save sends (buildTransactionPayload),
 * so the list and the save can't disagree. Null until there's a list to
 * ask for: both amounts, what arrived above 0 and no more than what left,
 * and a date.
 */
export function coinsPayload(values: TransactionFormData, book: AccountBook): ICreateTransactionPayload | null {
  if (!movesCoins(values, book)) return null;
  const from = parseDecimal(values.amountFrom);
  const to = parseDecimal(values.amountTo);
  const dated = Boolean(values.timestamp) && !Number.isNaN(new Date(values.timestamp).getTime());
  return to > 0 && from >= to && dated ? buildTransactionPayload(values, book) : null;
}

/** Where to ask: a new transfer's, or the edit of a saved one's. */
export function coinsUrl(transactionId: number | null | undefined): string {
  return transactionId ? `/transactions/${transactionId}/coins-moved` : "/transactions/coins-moved";
}

/** What the save does without a choice of coins, in decision 30's words
 * for the method (#713): the IRS default when none are identified (Treas.
 * Reg. §1.1012-1(j)), never a rule of its own. */
export function oldestFirstLine(book: AccountBook, fromId: number): string {
  return `Per-wallet FIFO: your oldest coins in ${accountName(book, fromId)} move first (the IRS default when you ` +
    "don't pick specific coins).";
}

// How the save's answers begin when it refuses: nothing was being saved here
const NOT_SAVED = /^Not (saved|changed): /;

/**
 * Why there's no list: the save's own refusal of the transfer as it is
 * (400, 422), else that the list can't be shown, with the server's reason
 * when it gave one; its "Not saved: " left out either way.
 */
export function noListLine(status: number | undefined, reason: string): string {
  const why = reason.replace(NOT_SAVED, "");
  if ((status === 400 || status === 422) && why) return `This transfer can't be saved as it is: ${why}`;
  return why ? `Which coins move can't be shown: ${why}` : "Which coins move can't be shown right now.";
}

/** The network fee's line: the save takes it from the oldest coins before
 * the coins that move (transaction._LotMove); none without a fee. */
export function feeLine(feeBtc: string | null): string | null {
  const fee = parseDecimal(feeBtc ?? undefined);
  if (!(fee > 0)) return null;
  return `The network fee, ${btcText(fee)} BTC, is paid first, from your oldest coins: a disposal at the fee's ` +
    "value, on Form 8949.";
}

/** "Mar 1, 2017": a date, read at UTC midnight so no timezone moves it (#185). */
export function acquiredText(coin: MovedCoin): string {
  const day = new Date(`${coin.acquired}T00:00:00Z`).toLocaleDateString(
    "en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });
  return coin.inherited ? `${day} (inherited)` : day;
}
