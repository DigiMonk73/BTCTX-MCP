// TEMPORARY (#793): the edit-save focus case 30 times, logging every focus change, to see on CI's
// Linux WebKit where focus goes when it isn't on Add transaction. Removed before the pull request.
import { createTx, expect, seedFunds, test } from "./fixtures";

type Logged = Window & { __log: string[] };

for (let i = 0; i < 30; i++) {
  test(`diag ${i}`, async ({ authedPage: page }) => {
    await seedFunds(page.request);
    await createTx(page.request, {
      type: "Deposit", timestamp: "2026-01-05T12:00:00Z", to_account_id: 1, from_account_id: 99,
      amount: "50", fee_amount: "0", fee_currency: "USD", source: "N/A",
    });
    await page.goto("/transactions");
    await page.getByLabel("Sort transactions").selectOption("CREATION_DESC");
    const edit = page.getByRole("listitem").first().getByRole("button", { name: "Edit" });
    await edit.focus();
    await page.keyboard.press("Enter");
    const panel = page.getByRole("dialog", { name: "Edit Transaction" });
    await panel.getByLabel("Amount", { exact: true }).fill("60");
    await page.evaluate(() => {
      const w = window as unknown as Logged;
      w.__log = [];
      const name = (el: EventTarget | null) => {
        if (!(el instanceof Element)) return String(el);
        const label = el.getAttribute("aria-label") ?? (el.textContent ?? "").trim().slice(0, 24);
        return `${el.tagName}${el.id ? `#${el.id}` : ""}(${label})${el.isConnected ? "" : " DETACHED"}`;
      };
      for (const kind of ["focusin", "focusout"]) {
        document.addEventListener(kind, (e) => w.__log.push(`${performance.now().toFixed(0)} ${kind} ${name(e.target)}`), true);
      }
    });
    await panel.getByRole("button", { name: "Update transaction" }).click();
    await expect(panel).toHaveCount(0);
    const add = page.getByRole("button", { name: "Add transaction" });
    try {
      await expect(add).toBeFocused({ timeout: 4000 });
    } catch {
      const log = await page.evaluate(() => (window as unknown as Logged).__log.join("\n"));
      const active = await page.evaluate(() => document.activeElement?.outerHTML.slice(0, 160));
      throw new Error(`#793 focus not on Add. active: ${active}\nlog:\n${log}`);
    }
  });
}
