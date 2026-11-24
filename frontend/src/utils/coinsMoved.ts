// Which coins a transaction moves, shown before it saves (#706): when to
// ask the server (POST /transactions/coins-moved, which runs the save's own
// path on a scratch copy of the ledger), with what, and the words around
// the list it gives. Asked with the body the Save sends, so the list
// follows a choice of coins (#711), and a Withdrawal from one of your
// wallets lists the coins that leave it, as a Transfer does; a Sell, and a
// Withdrawal from an exchange, list the coins they use, with each piece's
// proceeds, gain and term (#960).
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
  // A sale's or a spend's piece, as Form 8949 prints it (#960); a gift's has
  // a term only, and a Transfer's coins none of the three
  proceeds_usd?: string | null;
  gain_usd?: string | null;
  term?: "LONG" | "SHORT" | null;
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
 * chosen (#711). An exchange's leave oldest first: listed (#960), never chosen. */
export function leavesAWallet(values: FormAccounts, book: AccountBook): boolean {
  return values.type === "Withdrawal" && accountKind(book, chosenId(values.fromAccountId)) === "wallet";
}

/** A Sell, or a Withdrawal of bitcoin from an exchange as from a wallet:
 * the coins it disposes of are listed with what it realizes (#960). */
export function disposesOfCoins(values: FormAccounts, book: AccountBook): boolean {
  const fromId = chosenId(values.fromAccountId);
  return (values.type === "Sell" || values.type === "Withdrawal") && fromId !== undefined &&
    isBtcAccount(book, fromId);
}

/** Whether the form lists the coins a transaction takes. */
export function listsCoins(values: FormAccounts, book: AccountBook): boolean {
  return movesCoins(values, book) || leavesAWallet(values, book) || disposesOfCoins(values, book);
}

/**
 * The body to ask with: the one the Save sends (buildTransactionPayload),
 * so the list and the save can't disagree; a choice of coins that doesn't
 * add up yet (Save waits for it) asks as oldest first, so the answer still
 * says what the wallet holds. Null until there's a list to ask for: a
 * Transfer's two amounts (what arrived above 0 and no more than what left),
 * a Withdrawal's amount above 0, a Sell's BTC and proceeds above 0, and a
 * date.
 */
export function coinsPayload(values: TransactionFormData, book: AccountBook): ICreateTransactionPayload | null {
  if (!listsCoins(values, book)) return null;
  const dated = Boolean(values.timestamp) && !Number.isNaN(new Date(values.timestamp).getTime());
  if (!dated || !amountsToAsk(values)) return null;
  const payload = buildTransactionPayload(values, book);
  if (payload.chosen_coins && !addsUp(payload.chosen_coins, leaving(values))) payload.chosen_coins = null;
  return payload;
}

function amountsToAsk(values: TransactionFormData): boolean {
  if (values.type === "Transfer") {
    return parseDecimal(values.amountTo) > 0 && parseDecimal(values.amountFrom) >= parseDecimal(values.amountTo);
  }
  if (values.type === "Sell") {
    // Its proceeds start at $0: a list of losses before they're typed would
    // alarm more than it tells. A sale for $0 shows no list (a rare one)
    const proceeds = values.grossProceedsUSD;  // a number (valueAsNumber), NaN while blank
    return parseDecimal(values.amountBTC) > 0 && typeof proceeds === "number" && proceeds > 0;
  }
  return parseDecimal(values.amount) > 0;
}

/** Where to ask: a new transfer's, or the edit of a saved one's. */
export function coinsUrl(transactionId: number | null | undefined): string {
  return transactionId ? `/transactions/${transactionId}/coins-moved` : "/transactions/coins-moved";
}

/** What the save does without a choice of coins, in decision 30's words
 * for the method (#713): the IRS default when none are identified (Treas.
 * Reg. §1.1012-1(j)), never a rule of its own. */
export function oldestFirstLine(book: AccountBook, fromId: number, kind: TransactionType = "Transfer"): string {
  const go = kind === "Transfer" ? "move" : "leave";
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
  const what = kind === "Withdrawal" ? "withdrawal" : kind === "Sell" ? "sale" : "transfer";
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
