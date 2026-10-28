// Choosing which coins leave one of your wallets (#711; specific
// identification, Treas. Reg. §1.1012-1(j)(2)): where the form offers it,
// what leaves (in exact satoshis), when a choice adds up, the quick fills
// (the owner's Q3), and the words around the picker. The server checks the
// same rules (backend/services/chosen_coins.py); the picker only helps.
import { accountKind, chosenId, isBtcAccount } from "./accounts";
import { dayText, parseDecimal } from "./format";

/** What a wallet holds when the transaction comes, one purchase (or
 * deposit) per line, as the server lists it (transfer_coins._held). */
export interface HeldLine {
  acquired_txn_id: number | null; // null: a lot from before the upgrade, which the server replays first
  kind: string | null; // the acquisition's type: "Buy" or "Deposit"
  source: string | null; // a deposit's source, as listed ("MyBTC", "Gift"…)
  acquired_in: string | null; // the account it was bought or deposited into, not where its coins are now
  date: string | null; // the acquisition's date, YYYY-MM-DD in the tax timezone
  acquired: string; // its coins' date acquired, YYYY-MM-DD (holding period, Form 8949)
  inherited: boolean;
  btc: string;
  cost_usd: string;
  term: "SHORT" | "LONG"; // on the transaction's date
  oldest_first: string; // what oldest first takes of it
}

/** What leaves the wallet, in satoshis: everything, what moves or is sent, and the network fee. */
export interface Leaving {
  kind: "Transfer" | "Withdrawal";
  total: number;
  moved: number;
  fee: number;
}

const SATS = 100_000_000;
const SOURCE_WORDS: Record<string, string> = {
  MyBTC: "My BTC", Gift: "Gift", Inherited: "Inherited", Income: "Income", Interest: "Interest", Reward: "Reward",
  Rebate: "Rebate",
};

/** 7.1's words, always beside the picker. */
export const CHOOSE_RULE =
  "Choose coins only if you decided which coins to send by the time they left, and your records from then show " +
  "which purchases they were (a note you made, or coin control in your wallet with records tying its coins to " +
  "purchases). Otherwise the IRS counts the oldest coins as the ones that left (Treas. Reg. §1.1012-1(j)). A tax " +
  "professional can tell you whether your records are enough.";
export const DOESNT_ADD_UP =
  "The coins chosen must add up to what leaves: choose coins for all of it, or don't choose them.";
export const NOT_LISTED_IN_TIME = "BitcoinTX couldn't list this wallet's coins quickly enough here.";
export const NOT_A_NUMBER = "Each BTC chosen must be a plain number, with at most 8 decimal places.";

// A BTC field as typed: digits, at most one point, at most 8 places
const PLAIN_BTC = /^(\d+(\.\d{0,8})?|\.\d{1,8})$/;

/** Whether a line's BTC isn't a plain number of at most 8 places ("-0.1",
 * "0.1.2", "1e-3"): never read as some other amount. */
export function unreadable(lines: ChosenCoin[]): boolean {
  return lines.some((line) => line.btc !== "" && !PLAIN_BTC.test(line.btc));
}

/** A BTC value as whole satoshis, exact (a blank or unreadable one is 0). */
export function sats(value: BtcFieldValue | string | null | undefined): number {
  const btc = parseDecimal(value ?? undefined);
  return Number.isFinite(btc) ? Math.round(btc * SATS) : 0;
}

/** Satoshis as BTC in eight places, as the server writes them. */
export function btcEight(amount: number): string {
  return (amount / SATS).toFixed(8);
}

/** "0.10010000" as a field shows it: "0.1001". */
export function plainBtc(text: string): string {
  return text.includes(".") ? text.replace(/0+$/, "").replace(/\.$/, "") : text;
}

/** A Transfer out of one of your wallets to another account, or a
 * Withdrawal from one: an exchange's coins, a move within one wallet (only
 * its fee, oldest first), dollars and every other type take no choice. */
export function choosable(values: Pick<TransactionFormData, "type" | "fromAccountId" | "toAccountId">,
  book: AccountBook): boolean {
  const fromId = chosenId(values.fromAccountId);
  if (accountKind(book, fromId) !== "wallet") return false;
  if (values.type === "Withdrawal") return true;
  const toId = chosenId(values.toAccountId);
  return values.type === "Transfer" && toId !== undefined && toId !== fromId && isBtcAccount(book, toId);
}

/** What leaves: a Transfer's Amount (From), its fee in it, Amount (To)
 * arriving; a Withdrawal's amount and, on top, its fee. */
export function leaving(values: TransactionFormData): Leaving {
  if (values.type === "Transfer") {
    const total = sats(values.amountFrom);
    const moved = sats(values.amountTo);
    return { kind: "Transfer", total, moved, fee: Math.max(total - moved, 0) };
  }
  const moved = sats(values.amount);
  const fee = sats(values.fee);
  return { kind: "Withdrawal", total: moved + fee, moved, fee };
}

export function chosenTotal(lines: ChosenCoin[]): number {
  return lines.reduce((total, line) => total + sats(line.btc), 0);
}

/** Whether the coins chosen are exactly what leaves (never half a choice:
 * the server refuses one, as it would hide a rule for the rest). */
export function addsUp(lines: ChosenCoin[], leaves: Leaving): boolean {
  return leaves.total > 0 && chosenTotal(lines) === leaves.total;
}

/** The lines the save sends: the blank and 0 ones left out, each in eight places. */
export function sentLines(lines: ChosenCoin[]): ChosenCoin[] {
  return lines.filter((line) => sats(line.btc) > 0)
    .map((line) => ({ acquired_txn_id: line.acquired_txn_id, btc: btcEight(sats(line.btc)) }));
}

/** "Chosen 0.01010000 of 0.01010000 BTC: Amount (To) 0.01000000 and the
 * network fee 0.00010000.", in the form's own terms. */
export function runningTotal(lines: ChosenCoin[], leaves: Leaving): string {
  const head = `Chosen ${btcEight(chosenTotal(lines))} of ${btcEight(leaves.total)} BTC`;
  if (leaves.fee <= 0) return `${head}.`;
  const moved = leaves.kind === "Transfer" ? "Amount (To)" : "the amount";
  return `${head}: ${moved} ${btcEight(leaves.moved)} and the network fee ${btcEight(leaves.fee)}.`;
}

/** The quick fill "Oldest first": what the save takes without a choice. */
export function oldestFirst(held: HeldLine[]): ChosenCoin[] {
  return fill(held.filter((line) => sats(line.oldest_first) > 0).map((line) => [line, sats(line.oldest_first)]));
}

/** The quick fill "Highest cost first": the dearest coins a BTC first (the
 * smallest gain), which the IRS names as a way of identifying ((j)(4));
 * offered only on a transaction dated today (Q3). */
export function highestCostFirst(held: HeldLine[], leaves: Leaving): ChosenCoin[] {
  const perBtc = (line: HeldLine) => parseDecimal(line.cost_usd) / Math.max(parseDecimal(line.btc), 1e-8);
  const dearest = held.map((line, order) => ({ line, order }))
    .sort((a, b) => perBtc(b.line) - perBtc(a.line) || a.order - b.order);
  let left = leaves.total;
  const taken: Array<[HeldLine, number]> = [];
  for (const { line } of dearest) {
    const take = Math.min(sats(line.btc), left);
    if (take > 0) taken.push([line, take]);
    left -= take;
  }
  return fill(taken);
}

function fill(taken: Array<[HeldLine, number]>): ChosenCoin[] {
  return taken.filter(([line]) => line.acquired_txn_id !== null)
    .map(([line, amount]) => ({ acquired_txn_id: line.acquired_txn_id as number, btc: btcEight(amount) }));
}

/** "My BTC · Sparrow · Mar 1, 2017": how, where and when the coins were acquired. */
export function howAcquired(line: HeldLine): string {
  const how = line.kind === "Buy" ? "Buy" : SOURCE_WORDS[line.source ?? ""] ?? "Deposit";
  const when = line.date ? dayText(line.date) : null;
  return [how, line.acquired_in, when].filter(Boolean).join(" · ");
}

const day = (iso: string) => new Date(iso).toLocaleDateString(
  "en-US", { month: "short", day: "numeric", year: "numeric" });
const dayKey = (iso: string) => {
  const d = new Date(iso);
  return d.getFullYear() * 10000 + (d.getMonth() + 1) * 100 + d.getDate();
};

/** Whether a choice was made on a later day than the coins left. */
export function chosenLater(chosenAt: string, leftAt: string): boolean {
  return dayKey(chosenAt) > dayKey(leftAt);
}

/** "Chosen on <day>.", and 7.1's "Later" words when that's a later day
 * than the coins left: what counts is when the owner decided, not when
 * it's typed here (Q1). Days on this device's clock, as the form's times. */
export function chosenOn(chosenAt: string, leftAt: string): string {
  if (!chosenLater(chosenAt, leftAt)) return `Chosen on ${day(chosenAt)}.`;
  return `Chosen on ${day(chosenAt)}, after the coins left on ${day(leftAt)}. A choice counts only if you made it ` +
    "by then and your records show it.";
}

/** On an edit, a stored choice the save will set back to oldest first
 * (coins no longer being chosen, or a row that can no longer take a
 * choice): said, so no choice is dropped unseen. */
export function droppedChoice(values: TransactionFormData, book: AccountBook): string | null {
  if (!values.chosenCoinsSaved?.length) return null;
  if (choosable(values, book) && Array.isArray(values.chosenCoins)) return null;
  const when = values.coinsChosenAt ? ` on ${day(values.coinsChosenAt)}` : "";
  return `The coins chosen${when} go back to oldest first when you save.`;
}

/** Whether two choices are the same coins, whatever their order or notation. */
export function sameCoins(a: ChosenCoin[] | null | undefined, b: ChosenCoin[] | null | undefined): boolean {
  const key = (lines: ChosenCoin[] | null | undefined) =>
    sentLines(lines ?? []).map((line) => `${line.acquired_txn_id}:${line.btc}`).sort().join(",");
  return key(a) === key(b);
}
