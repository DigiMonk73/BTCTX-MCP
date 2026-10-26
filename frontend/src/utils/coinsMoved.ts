// Which coins a transaction moves, shown before it saves (#706): when to
// ask the server (POST /transactions/coins-moved, which runs the save's own
// path on a scratch copy of the ledger), with what, and the words around
// the list it gives. Asked with the body the Save sends, so the list
// follows a choice of coins (#711), and a Withdrawal from one of your
// wallets lists the coins that leave it, as a Transfer does.
import { accountKind, accountName, chosenId, isBtcAccount } from "./accounts";
import { addsUp, leaving, type HeldLine } from "./chosenCoins";
import { btcText, dayText, parseDecimal } from "./format";
import { buildTransactionPayload } from "./transactionForm";

/** A lot the save would put in the To account. */
export interface MovedCoin {
  acquired: string; // the date acquired, YYYY-MM-DD in the tax timezone
  btc: string;
  cost_usd: string;
  inherited: boolean;
  acquired_txn_id?: number | null; // the Buy or Deposit that acquired them (#711)
}

/** The server's answer: coins and fee_btc are null when it couldn't work
 * them out in time, or when a choice of coins isn't held then (detail says
 * which). From one of your wallets, `held` is what it holds then (#711). */
export interface CoinsMoved {
  coins: MovedCoin[] | null;
  fee_btc: string | null;
  detail: string | null;
  held?: HeldLine[] | null;
  dated_today?: boolean; // dated today in the tax timezone: "Highest cost first" may be offered (Q3)
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

/** A Withdrawal from one of your wallets: its coins leave, and can be
 * chosen (#711). An exchange's leave oldest first, and aren't listed. */
export function leavesAWallet(values: FormAccounts, book: AccountBook): boolean {
  return values.type === "Withdrawal" && accountKind(book, chosenId(values.fromAccountId)) === "wallet";
}

/** Whether the form lists the coins a transaction takes. */
export function listsCoins(values: FormAccounts, book: AccountBook): boolean {
  return movesCoins(values, book) || leavesAWallet(values, book);
}

/**
 * The body to ask with: the one the Save sends (buildTransactionPayload),
 * so the list and the save can't disagree; a choice of coins that doesn't
 * add up yet (Save waits for it) asks as oldest first, so the answer still
 * says what the wallet holds. Null until there's a list to ask for: a
 * Transfer's two amounts (what arrived above 0 and no more than what left),
 * a Withdrawal's amount above 0, and a date.
 */
export function coinsPayload(values: TransactionFormData, book: AccountBook): ICreateTransactionPayload | null {
  if (!listsCoins(values, book)) return null;
  const dated = Boolean(values.timestamp) && !Number.isNaN(new Date(values.timestamp).getTime());
  const amounts = values.type === "Transfer"
    ? parseDecimal(values.amountTo) > 0 && parseDecimal(values.amountFrom) >= parseDecimal(values.amountTo)
    : parseDecimal(values.amount) > 0;
  if (!dated || !amounts) return null;
  const payload = buildTransactionPayload(values, book);
  if (payload.chosen_coins && !addsUp(payload.chosen_coins, leaving(values))) payload.chosen_coins = null;
  return payload;
}

/** Where to ask: a new transfer's, or the edit of a saved one's. */
export function coinsUrl(transactionId: number | null | undefined): string {
  return transactionId ? `/transactions/${transactionId}/coins-moved` : "/transactions/coins-moved";
}

/** What the save does without a choice of coins, in decision 30's words
 * for the method (#713): the IRS default when none are identified (Treas.
 * Reg. §1.1012-1(j)), never a rule of its own. */
export function oldestFirstLine(book: AccountBook, fromId: number, kind: TransactionType = "Transfer"): string {
  const go = kind === "Withdrawal" ? "leave" : "move";
  return `Per-wallet FIFO: your oldest coins in ${accountName(book, fromId)} ${go} first (the IRS default when you ` +
    "don't pick specific coins).";
}

// How the save's answers begin when it refuses: nothing was being saved here
const NOT_SAVED = /^Not (saved|changed): /;

/**
 * Why there's no list: the save's own refusal of the transfer as it is
 * (400, 422), else that the list can't be shown, with the server's reason
 * when it gave one; its "Not saved: " left out either way.
 */
export function noListLine(status: number | undefined, reason: string, kind: TransactionType = "Transfer"): string {
  const why = reason.replace(NOT_SAVED, "");
  const what = kind === "Withdrawal" ? "withdrawal" : "transfer";
  if ((status === 400 || status === 422) && why) return `This ${what} can't be saved as it is: ${why}`;
  return why ? `Which coins move can't be shown: ${why}` : "Which coins move can't be shown right now.";
}

/** The network fee's line: the save takes it from the oldest coins before
 * the coins that move (transaction._LotMove), or from the oldest of the
 * coins chosen (#711); none without a fee. */
export function feeLine(feeBtc: string | null, chosen = false): string | null {
  const fee = parseDecimal(feeBtc ?? undefined);
  if (!(fee > 0)) return null;
  const from = chosen ? "the oldest of the coins you chose" : "your oldest coins";
  return `The network fee, ${btcText(fee)} BTC, is paid first, from ${from}: a disposal at the fee's value, on Form ` +
    "8949.";
}

/** "Mar 1, 2017": a date, read at UTC midnight so no timezone moves it (#185). */
export function acquiredText(coin: Pick<MovedCoin, "acquired" | "inherited"> & Partial<MovedCoin>): string {
  const day = dayText(coin.acquired);
  return coin.inherited ? `${day} (inherited)` : day;
}
