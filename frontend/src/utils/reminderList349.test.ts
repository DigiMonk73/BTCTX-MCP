import { describe, expect, it } from "vitest";
import { showTheList } from "./reminderList";

describe("a reminder's button names what it lists (#349)", () => {
  it("deposits for the dates originally acquired, sales for the 1099-DA's", () => {
    expect(showTheList("original_date_missing", 2)).toBe("Show the 2 deposits");
    expect(showTheList("original_date_missing", 1)).toBe("Show the 1 deposit");
    expect(showTheList("sale_may_differ_from_1099da", 1)).toBe("Show the 1 sale");
    expect(showTheList("sale_may_differ_from_1099da", 3)).toBe("Show the 3 sales");
  });

  it("transactions for one it doesn't know", () => {
    expect(showTheList("a_later_reminder", 2)).toBe("Show the 2 transactions");
  });
});
