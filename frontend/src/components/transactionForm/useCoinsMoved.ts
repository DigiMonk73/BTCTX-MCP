import axios from "axios";
import { useEffect, useState } from "react";
import api from "../../api";
import { serverReason } from "../../utils/apiError";
import { coinsUrl, type CoinsMoved } from "../../utils/coinsMoved";

/** How long the form waits after the last change before it asks: once the
 * typing stops, not for every key (a backdated transfer's list replays the
 * ledger on the server). */
export const COINS_WAIT_MS = 400;

/** The server's answer to the form's question: nothing to ask yet, the
 * question out, the list, or why there's none (the status it came with,
 * and its reason, "" when it gave none). */
export type CoinsState =
  | { kind: "idle" }
  | { kind: "asking" }
  | { kind: "listed"; answer: CoinsMoved }
  | { kind: "refused"; status: number | undefined; reason: string };

/** What the form shows: `stale` when it's the list for an earlier
 * question, kept while this one is asked so the form doesn't jump; only one
 * from the same account, whose coins they were. */
export interface CoinsShown {
  state: CoinsState;
  stale: boolean;
  /** Ask the same question again (a list that couldn't be worked out in time, #711) */
  retry: () => void;
}

/**
 * The coins a Transfer would move (#706), asked with `payload` (null: not
 * yet) once it has stayed the same for COINS_WAIT_MS. An answer counts only
 * for the question it answers: one that changed meanwhile is asked again,
 * its old request cancelled in the browser and its replay stopped on the
 * server (transfer_coins: the newest list asked for wins).
 */
export function useCoinsMoved(payload: ICreateTransactionPayload | null, transactionId?: number | null): CoinsShown {
  const url = coinsUrl(transactionId);
  const body = payload ? JSON.stringify(payload) : "";
  const [attempt, setAttempt] = useState(0);
  const question = body && `${url} ${body} ${attempt}`;
  const retry = () => setAttempt((n) => n + 1);
  const from = payload?.from_account_id;
  const [answered, setAnswered] = useState<{ question: string; url: string; from?: number; state: CoinsState } | null>(
    null);

  useEffect(() => {
    if (!question) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      api.post<CoinsMoved>(url, JSON.parse(body), { signal: controller.signal })
        .then((res): CoinsState => ({ kind: "listed", answer: res.data }))
        .catch((error: unknown): CoinsState => ({
          kind: "refused",
          status: axios.isAxiosError(error) ? error.response?.status : undefined,
          reason: serverReason(error) ?? "",
        }))
        .then((state) => {
          if (!controller.signal.aborted) setAnswered({ question, url, from, state });
        });
    }, COINS_WAIT_MS);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [question, url, body, from]);

  if (!question) return { state: { kind: "idle" }, stale: false, retry };
  if (answered?.question === question) return { state: answered.state, stale: false, retry };
  const sameCoins = answered?.url === url && answered.from === from;
  if (sameCoins && answered.state.kind === "listed" && (answered.state.answer.coins || answered.state.answer.held)) {
    return { state: answered.state, stale: true, retry };
  }
  return { state: { kind: "asking" }, stale: false, retry };
}
