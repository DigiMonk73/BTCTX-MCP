import { describe, expect, it } from "vitest";
import { satsFromBtc, satsFromUsd } from "./converter";
import { btcText } from "./format";

describe("the converter counts satoshis exactly (#451)", () => {
  it("counts a typed BTC amount from its digits", () => {
    // Each a float times 100,000,000 a hair under the whole satoshi (28,999,999.99…)
    expect(satsFromBtc("0.29")).toBe(29_000_000);
    expect(satsFromBtc("0.57")).toBe(57_000_000);
    expect(satsFromBtc("1.15")).toBe(115_000_000);
    expect(satsFromBtc("2.01")).toBe(201_000_000);
    expect(satsFromBtc("0.00000001")).toBe(1);
    expect(satsFromBtc("21000000")).toBe(2_100_000_000_000_000);
  });

  it("counts every amount to the cent of a bitcoin up to 21 BTC exactly", () => {
    for (let cents = 1; cents <= 2_100; cents++) {
      const text = (cents / 100).toFixed(2);
      expect(satsFromBtc(text), text).toBe(cents * 1_000_000);
    }
  });

  it("gets back the count the BTC field was written from", () => {
    for (const sats of [1, 99, 1_667, 28_999_999, 29_000_000, 123_456_789, 2_099_999_999_999_999]) {
      expect(satsFromBtc(btcText(sats / 100_000_000))).toBe(sats);
    }
  });

  it("rounds digits past the satoshi to the nearest", () => {
    expect(satsFromBtc("0.123456784")).toBe(12_345_678);
    expect(satsFromBtc("0.123456785")).toBe(12_345_679);
    expect(satsFromBtc("1.999999999")).toBe(200_000_000);
    expect(satsFromBtc("0.000000004")).toBe(0);
    expect(satsFromBtc("0.000000005")).toBe(1);
  });

  it("reads what a number field holds", () => {
    expect(satsFromBtc(".5")).toBe(50_000_000);
    expect(satsFromBtc("5.")).toBe(500_000_000);
    expect(satsFromBtc("00.29")).toBe(29_000_000);
    expect(satsFromBtc("-0.29")).toBe(-29_000_000);
    expect(satsFromBtc("1e-8")).toBe(1);
    expect(satsFromBtc("2.9E-1")).toBe(29_000_000);
    expect(satsFromBtc("5e-9")).toBe(1);
    expect(satsFromBtc("1e-10")).toBe(0);
    expect(satsFromBtc("-0")).toBe(0);
  });

  it("is no count when nothing readable is typed", () => {
    for (const text of ["", ".", "-", "e5", "1.2.3", "abc"]) expect(satsFromBtc(text), text).toBeNull();
  });

  it("counts dollars at a price once, to the nearest satoshi", () => {
    expect(satsFromUsd(1, 60_000)).toBe(1_667); // 1,666.67
    expect(satsFromUsd(2, 60_000)).toBe(3_333); // 3,333.33
    expect(satsFromUsd(600, 60_000)).toBe(1_000_000);
    expect(satsFromUsd(1, 70_000)).toBe(1_429); // 1,428.57
    expect(btcText(1_667 / 100_000_000)).toBe("0.00001667");
  });

  it("is no count without dollars or a price", () => {
    expect(satsFromUsd(0, 60_000)).toBeNull();
    expect(satsFromUsd(1, 0)).toBeNull();
  });
});
