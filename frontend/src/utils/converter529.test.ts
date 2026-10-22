import { describe, expect, it } from "vitest";
import { satsFromBtc, satsFromUsd, usdFromBtc, usdFromSats } from "./converter";

// The converter counts from the typed digits, and an exact half satoshi goes to the even
// count: the rule BitcoinTX keeps for a value worked out from a price (AGENTS.md, "Prices"; #556)
describe("the converter counts dollars at a price exactly, a half satoshi to the even count (#529)", () => {
  it("counts the issue's dollars: exactly 507,812.5 satoshis, to the even 507,812", () => {
    // 48,893 cents × 10^8 ÷ 9,628,160 cents; floats said 507,812.49999999994
    expect(satsFromUsd("488.93", 96_281.6)).toBe(507_812);
  });

  it("rounds an exact half down to an even count, and up to one", () => {
    expect(satsFromUsd("91.69", 80_000)).toBe(114_612); // 114,612.5; floats said 114,613
    expect(satsFromUsd("23.45", 60_032)).toBe(39_062); // 39,062.5; floats said 39,063
    expect(satsFromUsd("267.59", 80_000)).toBe(334_488); // 334,487.5; floats said 334,487
    expect(satsFromUsd("0.2588", 80_000)).toBe(324); // 323.5; floats said 323
    expect(satsFromUsd("0.01", 80_000)).toBe(12); // 12.5; floats said 13
    expect(satsFromUsd("0.03", 80_000)).toBe(38); // 37.5
  });

  it("counts amounts floats get wrong that aren't a half", () => {
    expect(satsFromUsd("20160000000", 96_281.95)).toBe(20_938_504_049_824); // floats said …825
    expect(satsFromUsd("5000000000", 96_021.83)).toBe(5_207_149_249_290); // floats said …291
  });

  it("counts all the bitcoin there is", () => {
    expect(satsFromUsd("2016000000000", 96_000)).toBe(2_100_000_000_000_000);
  });

  it("reads what a number field holds", () => {
    expect(satsFromUsd("6e2", 60_000)).toBe(1_000_000);
    expect(satsFromUsd(".6", 60_000)).toBe(1_000);
    expect(satsFromUsd("-91.69", 80_000)).toBe(-114_612);
    expect(satsFromUsd(" 1 ", 60_000)).toBe(1_667);
    expect(satsFromUsd("1", 0.5)).toBe(200_000_000);
  });

  it("is no count without dollars or a price", () => {
    for (const usd of ["", "0", "0.00", "-0", ".", "abc"]) expect(satsFromUsd(usd, 60_000), usd).toBeNull();
    expect(satsFromUsd("1", 0)).toBeNull();
  });
});

describe("a typed BTC amount's half satoshi goes to the even count too (#529)", () => {
  it("rounds an exact half past the satoshi to the even count", () => {
    expect(satsFromBtc("0.123456785")).toBe(12_345_678); // half up said 12,345,679
    expect(satsFromBtc("0.123456775")).toBe(12_345_678);
    expect(satsFromBtc("0.000000025")).toBe(2); // half up said 3
    expect(satsFromBtc("-0.000000025")).toBe(-2);
    expect(satsFromBtc("0.000000035")).toBe(4);
    expect(satsFromBtc("25e-9")).toBe(2);
  });

  it("rounds anything past a half to the nearest, as before", () => {
    expect(satsFromBtc("0.1234567850001")).toBe(12_345_679);
    expect(satsFromBtc("0.1234567849999")).toBe(12_345_678);
  });
});

// The server works a value out from a price as Decimal(price × amount).quantize(CENT): exact, an
// exact half cent to the even cent. The converter shows the cent BitcoinTX would save (#578)
describe("the converter's dollar figure is exact, a half cent to the even cent (#578)", () => {
  it("rounds an exact half cent to the even cent, down and up", () => {
    expect(usdFromBtc("0.5", 96_281.61)).toBe("48140.8"); // 48,140.805; floats said 48,140.81
    expect(usdFromBtc("0.15", 96_283.7)).toBe("14442.56"); // 14,442.555; floats said 14,442.55
    expect(usdFromSats("50000000", 96_281.61)).toBe("48140.8");
    expect(usdFromSats("15000000", 96_283.7)).toBe("14442.56");
  });

  it("counts amounts floats get wrong that aren't a half cent", () => {
    // 118,873,418,683.2249…; floats said 118,873,418,683.23
    expect(usdFromBtc("1234567.89012345", 96_287.47)).toBe("118873418683.22");
    expect(usdFromSats("123456789012345", 96_287.47)).toBe("118873418683.22");
  });

  it("writes the figure as the field did: no trailing zeros, 0 for less than half a cent", () => {
    expect(usdFromBtc("1", 50_000)).toBe("50000");
    expect(usdFromBtc("0.00001", 60_000)).toBe("0.6");
    expect(usdFromSats("250000", 60_000)).toBe("150");
    expect(usdFromSats("1", 60_000)).toBe("0"); // $0.0006
    expect(usdFromBtc("-0.5", 96_281.61)).toBe("-48140.8");
    expect(usdFromBtc("5e-1", 96_281.61)).toBe("48140.8");
  });

  it("is no figure without an amount or a price", () => {
    for (const text of ["", "0", "-0", ".", "abc"]) {
      expect(usdFromBtc(text, 60_000), text).toBe("");
      expect(usdFromSats(text, 60_000), text).toBe("");
    }
    expect(usdFromBtc("1", 0)).toBe("");
    expect(usdFromSats("1", 0)).toBe("");
  });
});
