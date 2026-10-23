// @vitest-environment jsdom
// The account book is loaded once per page and shared (2.0 spec 5.4); a
// failed load says so, and the next screen asks again.
import "../test/setup";
import { act, render, screen } from "@testing-library/react";
import type { AxiosResponse } from "axios";
import { beforeEach, describe, expect, it, vi } from "vitest";
import api from "../api";
import { ONE_OF_EACH } from "../test/books";
import { forgetAccounts, useAccounts } from "./useAccounts";

const Names: React.FC<{ label: string }> = ({ label }) => {
  const { book, failed } = useAccounts();
  const text = failed ? "failed" : book ? book.map((account) => account.name).join(", ") : "loading";
  return <p>{`${label}: ${text}`}</p>;
};

function answered(book: AccountBook): AxiosResponse<AccountBook> {
  return { data: book, status: 200, statusText: "OK", headers: {}, config: {} as AxiosResponse["config"] };
}

async function settle() {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

beforeEach(() => forgetAccounts());

describe("useAccounts", () => {
  it("asks GET /accounts/ once for every screen on the page", async () => {
    const get = vi.spyOn(api, "get").mockResolvedValue(answered(ONE_OF_EACH));
    render(<><Names label="form" /><Names label="list" /></>);
    await settle();
    expect(screen.getByText("form: Bank, Wallet, Exchange USD, Exchange BTC, BTC Fees, USD Fees")).toBeTruthy();
    expect(screen.getByText("list: Bank, Wallet, Exchange USD, Exchange BTC, BTC Fees, USD Fees")).toBeTruthy();
    expect(get.mock.calls.map(([url]) => url)).toEqual(["/accounts/"]);
  });

  it("says when the book won't load, and the next screen asks again", async () => {
    const get = vi.spyOn(api, "get").mockRejectedValueOnce(new Error("down")).mockResolvedValue(answered(ONE_OF_EACH));
    const first = render(<Names label="form" />);
    await settle();
    expect(screen.getByText("form: failed")).toBeTruthy();
    first.unmount();
    render(<Names label="again" />);
    await settle();
    expect(screen.getByText(/^again: Bank, Wallet/)).toBeTruthy();
    expect(get).toHaveBeenCalledTimes(2);
  });

  it("asks again after forgetAccounts (Settings, once it changes an account)", async () => {
    const get = vi.spyOn(api, "get").mockResolvedValue(answered(ONE_OF_EACH));
    const first = render(<Names label="form" />);
    await settle();
    first.unmount();
    forgetAccounts();
    render(<Names label="again" />);
    await settle();
    expect(get).toHaveBeenCalledTimes(2);
  });
});
