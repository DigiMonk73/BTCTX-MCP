// @vitest-environment jsdom
// Settings' account book (#355): the page's one book, then, after a change
// Settings made, the book as the server has it then.
import "../test/setup";
import { act, fireEvent, render, screen } from "@testing-library/react";
import type { AxiosResponse } from "axios";
import { beforeEach, describe, expect, it, vi } from "vitest";
import api from "../api";
import { MANY, ONE_OF_EACH } from "../test/books";
import { forgetAccounts, useAccounts } from "./useAccounts";
import { useSettingsAccounts } from "./useSettingsAccounts";

/** Settings, with a button standing for a change it made (an add, a hide, a delete). */
const Settings: React.FC = () => {
  const state = useSettingsAccounts();
  const text = state.failed ? "failed" : state.book ? `${state.book.length} accounts` : "loading";
  return <><p>{`settings: ${text}`}</p><button type="button" onClick={state.reload}>changed</button></>;
};

const reload = () => fireEvent.click(screen.getByRole("button", { name: "changed" }));

const Form: React.FC = () => {
  const { book } = useAccounts();
  return <p>{`form: ${book ? `${book.length} accounts` : "loading"}`}</p>;
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

describe("useSettingsAccounts", () => {
  it("shares the page's one book, and asks for it again after a change", async () => {
    const get = vi.spyOn(api, "get").mockResolvedValueOnce(answered(ONE_OF_EACH)).mockResolvedValue(answered(MANY));
    render(<><Settings /><Form /></>);
    await settle();
    expect(screen.getByText("settings: 6 accounts")).toBeTruthy();
    expect(get).toHaveBeenCalledTimes(1);

    act(() => reload());
    await settle();
    expect(screen.getByText("settings: 13 accounts")).toBeTruthy();
    expect(get).toHaveBeenCalledTimes(2);

    // A screen opened since asks again, so it sees the change too
    render(<Form />);
    await settle();
    expect(screen.getAllByText("form: 13 accounts")).toHaveLength(1);
    expect(get).toHaveBeenCalledTimes(3);
  });

  it("keeps the last asked: an answer that comes late is left out", async () => {
    let late: (value: AxiosResponse<AccountBook>) => void = () => {};
    vi.spyOn(api, "get")
      .mockResolvedValueOnce(answered(ONE_OF_EACH))
      .mockImplementationOnce(() => new Promise((resolve) => { late = resolve; }))
      .mockResolvedValue(answered(MANY));
    render(<Settings />);
    await settle();
    act(() => reload());
    act(() => reload());
    await settle();
    expect(screen.getByText("settings: 13 accounts")).toBeTruthy();
    late(answered(ONE_OF_EACH));
    await settle();
    expect(screen.getByText("settings: 13 accounts")).toBeTruthy();
  });

  it("settles once the book is there, so Settings can wait for it", async () => {
    let answer: (value: AxiosResponse<AccountBook>) => void = () => {};
    vi.spyOn(api, "get")
      .mockResolvedValueOnce(answered(ONE_OF_EACH))
      .mockImplementationOnce(() => new Promise((resolve) => { answer = resolve; }));
    let reloadNow: () => Promise<void> = async () => {};
    const Waiting: React.FC = () => {
      const state = useSettingsAccounts();
      return <button type="button" onClick={() => { reloadNow = state.reload; }}>{`${state.book?.length ?? 0}`}</button>;
    };
    render(<Waiting />);
    await settle();
    fireEvent.click(screen.getByRole("button"));
    let settled = false;
    const done = act(() => reloadNow().then(() => { settled = true; }));
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(settled).toBe(false);
    answer(answered(MANY));
    await done;
    expect(settled).toBe(true);
    expect(screen.getByRole("button").textContent).toBe("13");
  });

  it("says so when the book can't be had again", async () => {
    vi.spyOn(api, "get").mockResolvedValueOnce(answered(ONE_OF_EACH)).mockRejectedValue(new Error("down"));
    render(<Settings />);
    await settle();
    act(() => reload());
    await settle();
    expect(screen.getByText("settings: failed")).toBeTruthy();
  });
});
