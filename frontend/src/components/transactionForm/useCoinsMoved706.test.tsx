// @vitest-environment jsdom
// The list of the coins a Transfer moves (#706) answers the question the
// form asks now: a request for an older one is cancelled, and its answer,
// however late, is never shown.
import "../../test/setup";
import { act, renderHook } from "@testing-library/react";
import type { AxiosRequestConfig, AxiosResponse } from "axios";
import { afterEach, describe, expect, it, vi } from "vitest";
import api from "../../api";
import type { CoinsMoved } from "../../utils/coinsMoved";
import { COINS_WAIT_MS, useCoinsMoved, type CoinsShown } from "./useCoinsMoved";

const transfer = (amount: number) => ({
  type: "Transfer", timestamp: "2025-06-01T17:00:00.000Z", from_account_id: 2, to_account_id: 100, amount,
  fee_amount: 0, fee_currency: "BTC", cost_basis_usd: null,
}) as ICreateTransactionPayload;

const listOf = (btc: string): CoinsMoved => ({
  coins: [{ acquired: "2017-03-01", btc, cost_usd: "100.00", inherited: false }], fee_btc: "0.00000000", detail: null,
});

interface Asked {
  body: ICreateTransactionPayload;
  signal: AbortSignal | undefined;
  answer: (data: CoinsMoved) => void;
}

/** Every request for the list, answered only when the test says so. */
function stubPost(): Asked[] {
  const asked: Asked[] = [];
  vi.spyOn(api, "post").mockImplementation((_url: string, body?: unknown, config?: AxiosRequestConfig) =>
    new Promise<AxiosResponse>((resolve) => {
      asked.push({
        body: body as ICreateTransactionPayload,
        signal: config?.signal as AbortSignal | undefined,
        answer: (data) => resolve({ data, status: 200, statusText: "OK", headers: {}, config: {} } as AxiosResponse),
      });
    }));
  return asked;
}

const waitToAsk = () => act(() => new Promise((resolve) => setTimeout(resolve, COINS_WAIT_MS + 50)));

afterEach(() => vi.restoreAllMocks());

/** What the form shows: since #711 the hook also gives a retry. */
const shown = ({ state, stale }: CoinsShown) => ({ state, stale });

describe("the question the form asks now", () => {
  it("never shows a late answer to an older one", async () => {
    const asked = stubPost();
    const { result, rerender } = renderHook(({ payload }) => useCoinsMoved(payload), {
      initialProps: { payload: transfer(0.1) },
    });
    await waitToAsk();
    rerender({ payload: transfer(0.2) });
    await waitToAsk();
    expect(asked.map((a) => a.body.amount)).toEqual([0.1, 0.2]);
    expect(asked[0].signal?.aborted).toBe(true);

    await act(async () => asked[1].answer(listOf("0.20000000")));
    expect(shown(result.current)).toEqual({ state: { kind: "listed", answer: listOf("0.20000000") }, stale: false });
    await act(async () => asked[0].answer(listOf("0.10000000"))); // the older one, late
    expect(shown(result.current)).toEqual({ state: { kind: "listed", answer: listOf("0.20000000") }, stale: false });
  });

  it("asks nothing without a transfer to ask about", async () => {
    const asked = stubPost();
    const { result } = renderHook(() => useCoinsMoved(null));
    await waitToAsk();
    expect(asked).toEqual([]);
    expect(shown(result.current)).toEqual({ state: { kind: "idle" }, stale: false });
  });
});
