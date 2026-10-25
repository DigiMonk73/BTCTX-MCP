import React from "react";
import { useFormContext, useWatch } from "react-hook-form";
import { chosenId } from "../../utils/accounts";
import { choosable } from "../../utils/chosenCoins";
import { coinsPayload, feeLine, listsCoins, noListLine, oldestFirstLine } from "../../utils/coinsMoved";
import ChosenCoins from "./ChosenCoins";
import MovedCoinsTable from "./MovedCoinsTable";
import { useCoinsMoved, type CoinsShown } from "./useCoinsMoved";

/** What's being done, or why there's no list; nothing beside a list that's current. */
function statusLine({ state, stale }: CoinsShown, kind: TransactionType): React.ReactNode {
  const go = kind === "Withdrawal" ? "leave" : "move";
  if (state.kind === "asking" || stale) return <p className="field-hint">Working out which coins {go}…</p>;
  if (state.kind === "refused") return <p className="field-error">{noListLine(state.status, state.reason, kind)}</p>;
  if (state.kind === "listed" && state.answer.coins === null) {
    // A choice its wallet doesn't hold then is the save's refusal; past the time budget, only a note
    return <p className={state.answer.held ? "field-error" : "field-hint"}>{state.answer.detail}</p>;
  }
  return null;
}

/** The coins and the fee's line, dimmed while the list for the changed transaction is asked. */
function coinsList({ state, stale }: CoinsShown, kind: TransactionType, chosen: boolean): React.ReactNode {
  if (state.kind !== "listed" || !state.answer.coins?.length) return null;
  const fee = feeLine(state.answer.fee_btc, chosen);
  return (
    <div className="transfer-coins-list" aria-busy={stale}>
      <MovedCoinsTable coins={state.answer.coins}
        caption={kind === "Withdrawal" ? "Coins that will leave" : "Coins that will move"} />
      {fee && <p className="field-hint">{fee}</p>}
    </div>
  );
}

/**
 * Before a Transfer between two bitcoin accounts, or a Withdrawal from one
 * of your wallets, saves, the coins it takes (#706): the line saying which
 * go when you don't choose them, and the list the server gives of the coins
 * its save takes, asked with the body the Save sends. Leaving one of your
 * wallets, the coins can be chosen (#711, ChosenCoins). The status line
 * stays in place, so a screen reader hears it change (role="status"),
 * never the whole table again.
 */
const LeavingCoins: React.FC<{ book: AccountBook; transactionId?: number | null }> = ({ book, transactionId }) => {
  const { control } = useFormContext<TransactionFormData>();
  const values = useWatch({ control }) as TransactionFormData;
  const coins = useCoinsMoved(coinsPayload(values, book), transactionId);
  const fromId = chosenId(values.fromAccountId);
  if (!listsCoins(values, book) || fromId === undefined) return null;
  const canChoose = choosable(values, book);
  const choosing = canChoose && Array.isArray(values.chosenCoins);
  return (
    <div className="transfer-coins">
      <div>
        {!choosing && <p className="field-hint">{oldestFirstLine(book, fromId, values.type)}</p>}
        <div role="status">{statusLine(coins, values.type)}</div>
      </div>
      {coinsList(coins, values.type, choosing)}
      {canChoose && <ChosenCoins book={book} coins={coins} values={values} />}
    </div>
  );
};

export default LeavingCoins;
