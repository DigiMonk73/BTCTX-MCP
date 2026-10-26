// @vitest-environment jsdom
// Adding an exchange asks whether it sends a Form 1099-DA (#708), Yes
// chosen, so the answer is saved with it before any of its sales; a wallet
// or a bank is asked nothing of the kind.
import "../../test/setup";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import api from "../../api";
import { ONE_OF_EACH } from "../../test/books";
import { SWITCH_HELP } from "../../utils/ledgerAccounts";
import LedgerAccounts from "../LedgerAccounts";

const QUESTION = "Does this exchange send you a Form 1099-DA?";

/** The section on a fresh install's book, its Add form for `kind` open; every POST answered. */
async function openAdd(add: string) {
  vi.spyOn(api, "get").mockResolvedValue({ data: [] });
  const sent = vi.spyOn(api, "post").mockResolvedValue({ data: [] });
  render(<LedgerAccounts book={ONE_OF_EACH} failed={false} reload={vi.fn(async () => {})} />);
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: add }));
  return { sent, user };
}

describe("adding an exchange", () => {
  it("asks whether it sends a Form 1099-DA, Yes chosen, with the switch's own help", async () => {
    await openAdd("Add an exchange");
    const question = screen.getByRole("group", { name: QUESTION });
    expect((screen.getByRole("radio", { name: "Yes" }) as HTMLInputElement).checked).toBe(true);
    expect((screen.getByRole("radio", { name: "No" }) as HTMLInputElement).checked).toBe(false);
    expect(question.textContent).toContain(SWITCH_HELP);
  });

  it("sends No with the exchange", async () => {
    const view = await openAdd("Add an exchange");
    await view.user.type(screen.getByLabelText("Name"), "Abroad");
    await view.user.click(screen.getByRole("radio", { name: "No" }));
    await view.user.click(screen.getByRole("button", { name: "Add" }));
    await waitFor(() => expect(view.sent).toHaveBeenCalledTimes(1));
    expect(view.sent.mock.calls[0]).toEqual(["/accounts/", { kind: "exchange", name: "Abroad", sends_1099da: false }]);
  });

  it("sends Yes when it's left as it is", async () => {
    const view = await openAdd("Add an exchange");
    await view.user.type(screen.getByLabelText("Name"), "Kraken");
    await view.user.click(screen.getByRole("button", { name: "Add" }));
    await waitFor(() => expect(view.sent).toHaveBeenCalledTimes(1));
    expect(view.sent.mock.calls[0]).toEqual(["/accounts/", { kind: "exchange", name: "Kraken", sends_1099da: true }]);
  });
});

describe.each([["Add a wallet", "wallet"], ["Add a bank", "bank"]])("%s", (add, kind) => {
  it("asks nothing about a Form 1099-DA, and sends none", async () => {
    const view = await openAdd(add);
    expect(screen.queryByRole("group", { name: QUESTION })).toBeNull();
    await view.user.type(screen.getByLabelText("Name"), "Second");
    await view.user.click(screen.getByRole("button", { name: "Add" }));
    await waitFor(() => expect(view.sent).toHaveBeenCalledTimes(1));
    expect(view.sent.mock.calls[0]).toEqual(["/accounts/", { kind, name: "Second" }]);
  });
});
