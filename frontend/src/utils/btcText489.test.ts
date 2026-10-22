import { describe, expect, it } from "vitest";
import { btcText } from "./format";

describe("btcText keeps an exponent's zeros (#489)", () => {
  it("writes an amount from 10^21 BTC on as JavaScript does, whole", () => {
    // toFixed writes exponent form there ("1e+30"), and trimming trailing zeros took the exponent's
    expect(btcText(1e30)).toBe("1e+30");
    expect(btcText(1.5e50)).toBe("1.5e+50");
    expect(btcText(1e100)).toBe("1e+100");
    expect(btcText(-1e30)).toBe("-1e+30");
    expect(btcText(1e21)).toBe("1e+21");
  });

  it("still trims the zeros after the decimal point, and only those", () => {
    expect([10, 100, 21_000_000, 0.5, 0.1, 5e-8, 0].map(btcText)).toEqual(["10", "100", "21000000", "0.5", "0.1", "0.00000005", "0"]);
  });
});
