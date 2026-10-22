import { describe, expect, it } from "vitest";
import { satsFromBtc, satsFromUsd } from "./converter";

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
