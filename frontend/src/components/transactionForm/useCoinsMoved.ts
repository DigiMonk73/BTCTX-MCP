import { useEffect, useState } from "react";
import api from "../../api";
import { serverReason } from "../../utils/apiError";
import { coinsUrl, type CoinsMoved } from "../../utils/coinsMoved";

/** How long the form waits after the last change before it asks: once the
 * typing stops, not for every key (a backdated transfer's list replays the
 * ledger on the server). */
export const COINS_WAIT_MS = 400;

/** What the list shows: nothing to ask yet, the question out, the server's
 * answer, or why it has none ("" when it gave no reason). */
export type CoinsState =
  | { kind: "idle" }
  | { kind: "asking" }
  | { kind: "listed"; answer: CoinsMoved }
  | { kind: "refused"; reason: string };

/**
 * The coins a Transfer would move (#706), asked with `payload` (null: not
 * yet) once it has stayed the same for COINS_WAIT_MS. An answer counts only
 * for the question it answers: one that changed meanwhile is asked again,
 * its old request cancelled.
 */
export function useCoinsMoved(payload: ICreateTransactionPayload | null, transactionId?: number | null): CoinsState {
  const url = coinsUrl(transactionId);
  const body = payload ? JSON.stringify(payload) : "";
  const question = body && `${url} ${body}`;
  const [answered, setAnswered] = useState<{ question: string; state: CoinsState } | null>(null);

  useEffect(() => {
    if (!question) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      api.post<CoinsMoved>(url, JSON.parse(body), { signal: controller.signal })
        .then((res): CoinsState => ({ kind: "listed", answer: res.data }))
        .catch((error: unknown): CoinsState => ({ kind: "refused", reason: serverReason(error) ?? "" }))
        .then((state) => {
          if (!controller.signal.aborted) setAnswered({ question, state });
        });
    }, COINS_WAIT_MS);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [question, url, body]);

  if (!question) return { kind: "idle" };
  return answered?.question === question ? answered.state : { kind: "asking" };
}
