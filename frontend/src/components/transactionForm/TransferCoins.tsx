import React from "react";
import { useFormContext, useWatch } from "react-hook-form";
import { chosenId } from "../../utils/accounts";
import { coinsPayload, feeLine, movesCoins, noListLine, oldestFirstLine } from "../../utils/coinsMoved";
import MovedCoinsTable from "./MovedCoinsTable";
import { useCoinsMoved, type CoinsShown } from "./useCoinsMoved";

/** What's being done, or why there's no list; nothing beside a list that's current. */
function statusLine({ state, stale }: CoinsShown): React.ReactNode {
  if (state.kind === "asking" || stale) return <p className="field-hint">Working out which coins move…</p>;
  if (state.kind === "refused") return <p className="field-error">{noListLine(state.status, state.reason)}</p>;
  if (state.kind === "listed" && state.answer.coins === null) return <p className="field-hint">{state.answer.detail}</p>;
  return null;
}

/** The coins and the fee's line, dimmed while the list for the changed transfer is asked. */
function coinsList({ state, stale }: CoinsShown): React.ReactNode {
  if (state.kind !== "listed" || !state.answer.coins?.length) return null;
  const fee = feeLine(state.answer.fee_btc);
  return (
    <div className="transfer-coins-list" aria-busy={stale}>
      <MovedCoinsTable coins={state.answer.coins} />
      {fee && <p className="field-hint">{fee}</p>}
    </div>
  );
}

/**
 * Before a Transfer between two bitcoin accounts saves, the coins it will
 * move (#706; the owner's decision, 2026-10-25): the line saying which go
 * when you don't pick them, and the list the server gives of the coins its
 * save takes, asked with the body the Save sends. The status line stays in
 * place, so a screen reader hears it change (role="status"), never the
 * whole table again.
 */
const TransferCoins: React.FC<{ book: AccountBook; transactionId?: number | null }> = ({ book, transactionId }) => {
  const { control } = useFormContext<TransactionFormData>();
  const values = useWatch({ control }) as TransactionFormData;
  const coins = useCoinsMoved(coinsPayload(values, book), transactionId);
  const fromId = chosenId(values.fromAccountId);
  if (!movesCoins(values, book) || fromId === undefined) return null;
  return (
    <div className="transfer-coins">
      <div>
        <p className="field-hint">{oldestFirstLine(book, fromId)}</p>
        <div role="status">{statusLine(coins)}</div>
      </div>
      {coinsList(coins)}
    </div>
  );
};

export default TransferCoins;
