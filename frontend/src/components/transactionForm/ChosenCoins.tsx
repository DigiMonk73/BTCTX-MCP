import React, { useEffect } from "react";
import { useFormContext } from "react-hook-form";
import { accountName, chosenId } from "../../utils/accounts";
import {
  CHOOSE_RULE, DOESNT_ADD_UP, NOT_A_NUMBER, NOT_LISTED_IN_TIME, addsUp, btcEight, choosable, chosenLater, chosenOn,
  highestCostFirst, leaving, oldestFirst, plainBtc, runningTotal, sameCoins, sats, unreadable, type HeldLine,
  type Leaving,
} from "../../utils/chosenCoins";
import type { CoinsMoved } from "../../utils/coinsMoved";
import ChosenCoinsTable from "./ChosenCoinsTable";
import type { CoinsShown } from "./useCoinsMoved";

/** A fill's lines as the fields show them: "0.1001", not "0.10010000". */
const asTyped = (lines: ChosenCoin[]) => lines.map((line) => ({ ...line, btc: plainBtc(line.btc) }));

/** When the choice was made: an edit's stored day while it keeps those
 * coins; a new choice on a transaction already in the past is made today,
 * after the coins left, which 7.1's words say (Q1). None for a new choice
 * made the day the coins leave. */
function chosenOnLine(values: TransactionFormData, lines: ChosenCoin[]): string | null {
  const left = new Date(values.timestamp);
  if (Number.isNaN(left.getTime())) return null;
  const kept = Boolean(values.coinsChosenAt) && sameCoins(lines, values.chosenCoinsSaved);
  const at = kept ? (values.coinsChosenAt as string) : new Date().toISOString();
  return kept || chosenLater(at, left.toISOString()) ? chosenOn(at, left.toISOString()) : null;
}

interface PickerParts {
  held: HeldLine[] | null;
  answer: CoinsMoved | null;
  /** The answer is for the transaction as it was a moment ago */
  stale: boolean;
  set: (next: ChosenCoin[] | null) => void;
  retry: () => void;
}

/** Shut: the button that opens it, filled oldest first, once the wallet's
 * coins are listed; or "Try again" when they couldn't be in time. */
const ShutPicker: React.FC<PickerParts> = ({ held, answer, set, retry }) => {
  if (held?.length) {
    return <div className="coins-picker-open"><button type="button" className="btn btn-secondary btn-sm"
      onClick={() => set(asTyped(oldestFirst(held)))}>Choose which coins leave</button></div>;
  }
  return answer && answer.coins === null && !held
    ? <div className="coins-picker-open">
      <button type="button" className="btn btn-quiet btn-sm" onClick={retry}>Try again</button>
    </div>
    : null;
};

/** The quick fills (Q3: "Highest cost first" only on a transaction dated
 * today, never from the answer for the transaction as it was a moment
 * ago, whose date may have been today), "Try again" when the coins
 * couldn't be listed, and shutting it. */
const PickerActions: React.FC<PickerParts & { leaves: Leaving }> = ({ held, answer, stale, set, retry, leaves }) => (
  <div className="coins-picker-actions">
    {held && (
      <button type="button" className="btn btn-quiet btn-sm" onClick={() => set(asTyped(oldestFirst(held)))}>
        Oldest first
      </button>
    )}
    {held && answer?.dated_today && !stale && (
      <button type="button" className="btn btn-quiet btn-sm"
        onClick={() => set(asTyped(highestCostFirst(held, leaves)))}>Highest cost first</button>
    )}
    {answer && !held && <button type="button" className="btn btn-quiet btn-sm" onClick={retry}>Try again</button>}
    <button type="button" className="btn btn-quiet btn-sm" onClick={() => set(null)}>Don&apos;t choose coins</button>
  </div>
);

/** The lines of a stored choice the wallet's list doesn't show (it
 * couldn't be worked out in time, or the edit moved the coins away). */
const UnlistedLines: React.FC<{ lines: ChosenCoin[] }> = ({ lines }) => lines.length === 0 ? null : (
  <ul className="coins-picker-unlisted">
    {lines.map((line) => (
      <li key={line.acquired_txn_id}>Transaction {line.acquired_txn_id}: {btcEight(sats(line.btc))} BTC</li>
    ))}
  </ul>
);

/**
 * Choosing which coins leave one of your wallets (#711; specific
 * identification, Treas. Reg. §1.1012-1(j)(2)). Shut, a button opens it on
 * what the wallet holds then, filled oldest first (the IRS's default);
 * open, a line per purchase with a BTC field, the quick fills, the rule's
 * words, the running total, and the day it was chosen. Save waits until it
 * adds up to what leaves. The choice is the form's chosenCoins: null shut
 * (oldest first).
 */
const ChosenCoins: React.FC<{ book: AccountBook; coins: CoinsShown; values: TransactionFormData }> = (
  { book, coins, values }) => {
  const { register, setValue, formState: { errors, isSubmitted } } = useFormContext<TransactionFormData>();
  useEffect(() => {
    register("chosenCoins", {
      validate: (lines, all) => {
        if (!Array.isArray(lines) || !choosable(all, book)) return true;
        if (unreadable(lines)) return NOT_A_NUMBER;
        return addsUp(lines, leaving(all)) || DOESNT_ADD_UP;
      },
    });
  }, [register, book]);
  const answer = coins.state.kind === "listed" ? coins.state.answer : null;
  const held = answer?.held ?? null;
  const set = (next: ChosenCoin[] | null) =>
    setValue("chosenCoins", next, { shouldDirty: true, shouldValidate: isSubmitted });
  const parts = { held, answer, stale: coins.stale, set, retry: coins.retry };
  const lines = values.chosenCoins;
  if (!Array.isArray(lines)) return <ShutPicker {...parts} />;

  const wallet = accountName(book, chosenId(values.fromAccountId) ?? 0);
  const leaves = leaving(values);
  const listed = new Set(held?.map((line) => line.acquired_txn_id));
  const when = chosenOnLine(values, lines);
  return (
    <fieldset className="coins-picker">
      <legend className="field-label">Choose which coins leave {wallet}</legend>
      <p className="field-hint">{CHOOSE_RULE}</p>
      {when && <p className="field-hint">{when}</p>}
      {held && <ChosenCoinsTable held={held} lines={lines} wallet={wallet} onChange={set} />}
      {answer && !held && <p className="field-hint">{NOT_LISTED_IN_TIME}</p>}
      <UnlistedLines lines={lines.filter((line) => !listed.has(line.acquired_txn_id) && sats(line.btc) > 0)} />
      <PickerActions {...parts} leaves={leaves} />
      <p className="field-hint" aria-live="polite">{runningTotal(lines, leaves)}</p>
      {errors.chosenCoins && <span className="field-error">{errors.chosenCoins.message}</span>}
    </fieldset>
  );
};

export default ChosenCoins;
