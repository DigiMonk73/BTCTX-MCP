import React from "react";
import { useFormContext, useWatch } from "react-hook-form";
import { chosenId } from "../../utils/accounts";
import { coinsPayload, feeLine, movesCoins, noListLine, oldestFirstLine } from "../../utils/coinsMoved";
import MovedCoinsTable from "./MovedCoinsTable";
import { useCoinsMoved, type CoinsShown } from "./useCoinsMoved";

/** Below the line: the list and the fee's line, or why there's no list.
 * The lines say what changed to a screen reader (role="status"), never the
 * whole table again. */
function shown({ state, stale }: CoinsShown): React.ReactNode {
  switch (state.kind) {
    case "asking":
      return <p className="field-hint" role="status">Working out which coins move…</p>;
    case "refused":
      return <p className="field-error" role="status">{noListLine(state.status, state.reason)}</p>;
    case "listed": {
      const { coins, detail, fee_btc } = state.answer;
      if (coins === null) return <p className="field-hint" role="status">{detail}</p>;
      if (coins.length === 0) return null;
      const fee = feeLine(fee_btc);
      return (
        <>
          <MovedCoinsTable coins={coins} stale={stale} />
          {fee && <p className="field-hint">{fee}</p>}
        </>
      );
    }
    default:
      return null;
  }
}

/**
 * Before a Transfer between two bitcoin accounts saves, the coins it will
 * move (#706; the owner's decision, 2026-10-25): the line saying which go
 * when you don't pick them, and the list the server gives of the coins its
 * save takes, asked with the body the Save sends.
 */
const TransferCoins: React.FC<{ book: AccountBook; transactionId?: number | null }> = ({ book, transactionId }) => {
  const { control } = useFormContext<TransactionFormData>();
  const values = useWatch({ control }) as TransactionFormData;
  const coins = useCoinsMoved(coinsPayload(values, book), transactionId);
  const fromId = chosenId(values.fromAccountId);
  if (!movesCoins(values, book) || fromId === undefined) return null;
  return (
    <div className="transfer-coins">
      <p className="field-hint">{oldestFirstLine(book, fromId)}</p>
      {shown(coins)}
    </div>
  );
};

export default TransferCoins;
