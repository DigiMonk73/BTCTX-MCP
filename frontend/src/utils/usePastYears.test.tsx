// @vitest-environment jsdom
// B6b-11's proving test: a write through the past-year warning (spec 5.8,
// utils/usePastYears.tsx). Its 409 opens the dialog; Save anyway sends the same
// write again with the 409's fingerprint; a new 409 (the ledger changed
// meanwhile) asks again; Cancel saves nothing. An add to years whose box was
// ticked is confirmed without asking, with each 409's own fingerprint; edits
// and deletes always ask.
import "../test/setup";
import React from "react";
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AxiosError, type AxiosResponse } from "axios";
import { afterEach, describe, expect, it, vi } from "vitest";
import { askForAddsAgain } from "./pastYears";
import { usePastYears, type PastYears } from "./usePastYears";

const SAVE = "Save anyway (a copy is made first)";
const BOX = /^Don't ask again for adds to/;

function warning(years: number[], confirm: string): AxiosError {
  const data = { detail: `This changes the figures of tax year ${years[0]}…`, years, changes: [], pending: [],
    recalc_error: null, confirm };
  const response = { data, status: 409, statusText: "", headers: {}, config: {} } as AxiosResponse;
  return new AxiosError("failed", "ERR_BAD_REQUEST", undefined, undefined, response);
}

/** A screen that makes writes: the hook's `through`, and its dialog rendered. */
function mount(): { hook: () => PastYears } {
  let current: PastYears | null = null;
  const Screen: React.FC = () => {
    current = usePastYears();
    return <div>{current.dialog}</div>;
  };
  render(<Screen />);
  return { hook: () => current as unknown as PastYears };
}

/** `answers` in turn: an error is thrown, anything else returned. */
function sender(...answers: unknown[]) {
  return vi.fn(async (confirm?: string) => {
    void confirm;
    const next = answers.shift();
    if (next instanceof Error) throw next;
    return next;
  });
}

/** Start a write, and let it run up to its dialog (or its end): its answer, still to come while it asks. */
async function start<T>(hook: () => PastYears, send: (confirm?: string) => Promise<T>, forAdd: boolean) {
  let result: Promise<T | null> = Promise.resolve(null);
  await act(async () => {
    result = hook().through(send, forAdd);
    result.catch(() => undefined); // a refusal is awaited by the test, never left unhandled
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
  return { result };
}

afterEach(() => askForAddsAgain());

describe("usePastYears", () => {
  it("a write that isn't asked about is its answer, with no dialog", async () => {
    const { hook } = mount();
    const send = sender("saved");
    await expect((await start(hook, send, false)).result).resolves.toBe("saved");
    expect(send).toHaveBeenCalledTimes(1);
    expect(send).toHaveBeenCalledWith(undefined);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("asks on the 409, and Save anyway sends it again with the fingerprint", async () => {
    const { hook } = mount();
    const send = sender(warning([2025], "fp-1"), "saved");
    const { result } = await start(hook, send, false);
    expect(screen.getByRole("dialog")).toHaveAccessibleName("Change an earlier tax year?");
    await userEvent.click(screen.getByRole("button", { name: SAVE }));
    await expect(result).resolves.toBe("saved");
    expect(send.mock.calls).toEqual([[undefined], ["fp-1"]]);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("Cancel sends nothing more: null", async () => {
    const { hook } = mount();
    const send = sender(warning([2025], "fp-1"), "saved");
    const { result } = await start(hook, send, false);
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await expect(result).resolves.toBeNull();
    expect(send).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("a new 409 to the confirmed write asks again, and its fingerprint is sent", async () => {
    const { hook } = mount();
    const send = sender(warning([2025], "fp-1"), warning([2024, 2025], "fp-2"), "saved");
    const { result } = await start(hook, send, false);
    await userEvent.click(screen.getByRole("button", { name: SAVE }));
    expect(await screen.findByRole("dialog")).toHaveAccessibleDescription(/tax year 2024/);
    await userEvent.click(screen.getByRole("button", { name: SAVE }));
    await expect(result).resolves.toBe("saved");
    expect(send.mock.calls).toEqual([[undefined], ["fp-1"], ["fp-2"]]);
  });

  it("any other error is thrown as it came, with no dialog", async () => {
    const { hook } = mount();
    const refusal = new Error("Not changed: later transactions depend on this one.");
    const { result } = await start(hook, sender(refusal), false);
    await expect(result).rejects.toBe(refusal);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("only an add offers the box", async () => {
    const { hook } = mount();
    void ((await start(hook, sender(warning([2025], "fp-1"), "saved"), false)).result);
    expect(screen.queryByRole("checkbox", { name: BOX })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    void ((await start(hook, sender(warning([2025], "fp-1"), "saved"), true)).result);
    expect(screen.getByRole("checkbox", { name: BOX })).toBeInTheDocument();
  });

  it("with the box ticked, the next adds to that year confirm their own 409 without asking", async () => {
    const { hook } = mount();
    const { result: first } = await start(hook, sender(warning([2025], "fp-1"), "one"), true);
    await userEvent.click(screen.getByRole("checkbox", { name: BOX }));
    await userEvent.click(screen.getByRole("button", { name: SAVE }));
    await expect(first).resolves.toBe("one");

    const next = sender(warning([2025], "fp-7"), "two");
    await expect((await start(hook, next, true)).result).resolves.toBe("two");
    expect(next.mock.calls).toEqual([[undefined], ["fp-7"]]); // its own 409 first: never sent blind
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("an add to another year, or an edit of that year, still asks", async () => {
    const { hook } = mount();
    const { result: first } = await start(hook, sender(warning([2025], "fp-1"), "one"), true);
    await userEvent.click(screen.getByRole("checkbox", { name: BOX }));
    await userEvent.click(screen.getByRole("button", { name: SAVE }));
    await first;

    void ((await start(hook, sender(warning([2024], "fp-2"), "two"), true)).result);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    void ((await start(hook, sender(warning([2025], "fp-3"), "three"), false)).result);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("an add whose box wasn't ticked asks next time too", async () => {
    const { hook } = mount();
    const { result: first } = await start(hook, sender(warning([2025], "fp-1"), "one"), true);
    await userEvent.click(screen.getByRole("button", { name: SAVE }));
    await first;
    void ((await start(hook, sender(warning([2025], "fp-2"), "two"), true)).result);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
});
