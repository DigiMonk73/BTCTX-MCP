// A gift, donation or lost coins has no proceeds (#457): the form saved a
// hidden $0 on one (`?? 0`), and made a Spent later without proceeds it was
// a $0 sale. The form now sends a withdrawal's proceeds only for a Spent,
// and shows another withdrawal's $0 blank, so making it a Spent prices it.
import { describe, expect, it } from "vitest";
import { buildTransactionPayload, mapTransactionToFormData } from "./transactionForm";
import { ONE_OF_EACH } from "../test/accountBooks";

const gift = {
  id: 1,
  type: "Withdrawal",
  timestamp: "2024-06-10T15:20:00Z",
  from_account_id: 2,
  to_account_id: 99,
  amount: 0.1,
  fee_amount: 0,
  fee_currency: "BTC",
  purpose: "Gift",
  cost_basis_usd: 4000,
  proceeds_usd: undefined,
  gross_proceeds_usd: undefined,
  realized_gain_usd: 0,
} as unknown as ITransaction;

function form(fields: Partial<ITransaction>) {
  return mapTransactionToFormData({ ...gift, ...fields } as ITransaction, ONE_OF_EACH);
}

describe("a gift's proceeds (#457)", () => {
  it.each(["Gift", "Donation", "Lost", " gift "])("a %s saved unchanged sends none", (purpose) => {
    const body = buildTransactionPayload(form({ purpose }), ONE_OF_EACH);
    expect(body.proceeds_usd).toBeUndefined();
    expect(body.gross_proceeds_usd).toBeUndefined();
    expect(JSON.stringify(body)).not.toContain("proceeds");
  });

  it("an older form's $0 shows blank, so making it a Spent sends blank: the hour's price", () => {
    const opened = form({ gross_proceeds_usd: 0 });
    expect(opened.proceeds_usd).toBeUndefined();
    expect(buildTransactionPayload({ ...opened, purpose: "Spent" }, ONE_OF_EACH).proceeds_usd).toBeNull();
  });

  it("a former spend's proceeds show, and making it a Spent again sends them", () => {
    const opened = form({ gross_proceeds_usd: 3600 });
    expect(opened.proceeds_usd).toBe(3600);
    expect(buildTransactionPayload(opened, ONE_OF_EACH).proceeds_usd).toBeUndefined();
    expect(buildTransactionPayload({ ...opened, purpose: "Spent" }, ONE_OF_EACH).proceeds_usd).toBe(3600);
  });

  it("a Spent's proceeds are sent as before, a typed $0 included", () => {
    expect(buildTransactionPayload(form({ purpose: "Spent", gross_proceeds_usd: 3600 }), ONE_OF_EACH).proceeds_usd).toBe(3600);
    // As one is saved: a $0 gross, so $0 proceeds
    expect(buildTransactionPayload(form({ purpose: "Spent", gross_proceeds_usd: 0, proceeds_usd: 0 }), ONE_OF_EACH).proceeds_usd).toBe(0);
  });

  it("a dollar withdrawal shows none and sends none (#449)", () => {
    const dollars = form({ from_account_id: 1, purpose: "N/A", fee_currency: "USD", gross_proceeds_usd: 250 });
    expect(dollars.proceeds_usd).toBeUndefined();
    expect(buildTransactionPayload(dollars, ONE_OF_EACH).proceeds_usd).toBeNull();
    // Moved to a bitcoin account in the form and made a Spent: blank, the hour's price
    const moved = { ...dollars, account: "Wallet" as AccountType, currency: "BTC" as Currency, purpose: "Spent" as WithdrawalPurpose };
    expect(buildTransactionPayload(moved, ONE_OF_EACH).proceeds_usd).toBeNull();
  });
});
