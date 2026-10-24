// @vitest-environment jsdom
// An exchange's 1099-DA switch in Settings (#355, 2.0 spec 5.9): what's
// saved is what the box shows, whatever the server answers; the other
// changes wait while it saves; Ledger Review is asked again once it's saved.
// The past-year dialog's own round is in e2e/settings-accounts-355.e2e.ts.
import "../../test/setup";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AxiosError, type AxiosResponse } from "axios";
import { describe, expect, it, vi } from "vitest";
import api from "../../api";
import { ONE_OF_EACH } from "../../test/books";
import LedgerAccounts from "../LedgerAccounts";

const BOOK = ONE_OF_EACH.map((a) => ({ ...a, in_use: true }));

function refused(status: number, detail: string): AxiosError {
  const response = { data: { detail }, status, statusText: "", headers: {}, config: {} } as AxiosResponse;
  return new AxiosError(`Request failed with status code ${status}`, "ERR_BAD_REQUEST", undefined, undefined, response);
}

/** The section on BOOK, the Exchange's details open; each switch's PUT answered by `put`. */
async function mount(put: () => Promise<unknown>) {
  vi.spyOn(api, "get").mockResolvedValue({ data: [] });
  const sent = vi.spyOn(api, "put").mockImplementation(put);
  const reload = vi.fn(async () => {});
  const saved = vi.fn();
  render(<LedgerAccounts book={BOOK} failed={false} reload={reload} onFiguresChanged={saved} />);
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: /^Exchange\b/ }));
  const box = screen.getByLabelText("This exchange sends me a Form 1099-DA") as HTMLInputElement;
  return { sent, reload, saved, user, box };
}

describe("an exchange's 1099-DA switch", () => {
  it("saves at once when no earlier year moves, then reads the book and Ledger Review again", async () => {
    const view = await mount(async () => ({ data: {} }));
    expect(view.box.checked).toBe(true);
    await view.user.click(view.box);
    await waitFor(() => expect(view.reload).toHaveBeenCalledTimes(1));
    expect(view.sent.mock.calls.map(([url, body, config]) => [url, body, config])).toEqual([
      ["/accounts/4", { sends_1099da: false }, undefined],
    ]);
    expect(view.saved).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("shows a refusal in the server's words, the box as saved, and reads the book again all the same", async () => {
    const view = await mount(async () => { throw refused(400, "Only an exchange's account has a 1099-DA switch."); });
    await view.user.click(view.box);
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", "Only an exchange's account has a 1099-DA switch.");
    expect(view.box.checked).toBe(true);
    expect(view.reload).toHaveBeenCalledTimes(1);
    expect(view.saved).not.toHaveBeenCalled();
  });

  it("takes one change at a time: a second click and the row's other buttons wait while it saves", async () => {
    let answer: (value: unknown) => void = () => {};
    const view = await mount(() => new Promise((resolve) => { answer = resolve; }));
    await view.user.click(view.box);
    expect((screen.getByRole("button", { name: "Hide" }) as HTMLButtonElement).disabled).toBe(true);
    await view.user.click(view.box);
    expect(view.sent).toHaveBeenCalledTimes(1);
    await act(async () => answer({ data: {} }));
    await waitFor(() => expect((screen.getByRole("button", { name: "Hide" }) as HTMLButtonElement).disabled).toBe(false));
    expect(view.sent).toHaveBeenCalledTimes(1);
  });
});
