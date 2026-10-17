import { describe, expect, it } from "vitest";
import { CLEARED, ERROR, pressKey } from "./calculator";

/** What the display shows after these keys, from a cleared calculator. */
function shows(keys: string): string {
  return [...keys].reduce(pressKey, CLEARED).display;
}

describe("the sidebar calculator (#450)", () => {
  it("keeps the running total through a chain of operations", () => {
    expect(shows("2+3+4=")).toBe("9");
    expect(shows("2+3+")).toBe("5");
    expect(shows("10-3-2=")).toBe("5");
    // Left to right, as a pocket calculator works: no × before +
    expect(shows("2+3*4=")).toBe("20");
    expect(shows("2*3+4=")).toBe("10");
  });

  it("goes on from a result with an operator", () => {
    expect(shows("2+3=+4=")).toBe("9");
    expect(shows("2+3=*2=")).toBe("10");
  });

  it("takes the second of two operators in a row", () => {
    expect(shows("5++1=")).toBe("6");
    expect(shows("5+-1=")).toBe("4");
    expect(shows("5+")).toBe("5");
  });

  it("starts a new number with a digit after =", () => {
    expect(shows("2+3=7")).toBe("7");
    expect(shows("2+3=7+1=")).toBe("8");
    expect(shows("2+3=.5")).toBe("0.5");
  });

  it("ignores a second decimal point", () => {
    expect(shows("1.2.3")).toBe("1.23");
    expect(shows("1.2.3+1=")).toBe("2.23");
    expect(shows(".")).toBe("0.");
    expect(shows("..5")).toBe("0.5");
  });

  it("drops leading zeros, but not the zero before a point", () => {
    expect(shows("007")).toBe("7");
    expect(shows("0.05")).toBe("0.05");
    expect(shows("5+007=")).toBe("12");
  });

  it("rounds away a computer's binary noise", () => {
    expect(shows(".1+.2=")).toBe("0.3");
    expect(shows("1.1*1.1=")).toBe("1.21");
    expect(shows("1.005*1000=")).toBe("1005");
    expect(shows(".3/.1=")).toBe("3");
    // Where most of the digits cancel out
    expect(shows("1000000.1-1000000=")).toBe("0.1");
    expect(shows("100.1-100=")).toBe("0.1");
  });

  it("keeps every digit a sum of bitcoin amounts or sats has", () => {
    expect(shows("0.12345678+1.87654321=")).toBe("1.99999999");
    expect(shows("2100000000000000+1=")).toBe("2100000000000001");
    expect(shows("0.00000001*5=")).toBe("0.00000005"); // never 5e-8 (#101)
    expect(shows("0.00000001-0.00000001=")).toBe("0");
  });

  it("gives a division that doesn't end its first 15 digits", () => {
    expect(shows("1/3=")).toBe("0.333333333333333");
    expect(shows("2/3=")).toBe("0.666666666666667");
    expect(shows("100/3=")).toBe("33.3333333333333");
    expect(shows("1/4=")).toBe("0.25");
  });

  it("writes a result with at most 16 decimals, so it fits the display", () => {
    expect(shows("0.00000001/3=")).toBe("0.0000000033333333");
    expect(shows("0-0.00000001/3=")).toBe("-0.0000000033333333");
    expect(shows("0.00000001*0.00000001=")).toBe("0.0000000000000001");
    expect(shows("0.00000001*0.000000001=")).toBe("0");
  });

  it("shows an error for a division by zero, never Infinity", () => {
    expect(shows("1/0=")).toBe(ERROR);
    expect(shows("0/0=")).toBe(ERROR);
    expect(shows("1/0+")).toBe(ERROR);
  });

  it("starts again after an error with a digit, ignoring operators and =", () => {
    expect(shows("1/0=5")).toBe("5");
    expect(shows("1/0=5+1=")).toBe("6");
    expect(shows("1/0=+=")).toBe(ERROR);
    expect(shows("1/0=*2=")).toBe("2");
    expect(shows("1/0=.5")).toBe("0.5");
  });

  it("drops an operator with no number after it at =", () => {
    expect(shows("5+=")).toBe("5");
    expect(shows("5+==")).toBe("5");
    expect(shows("2+3==")).toBe("5");
  });

  it("clears everything with C", () => {
    expect(shows("2+3C")).toBe("0");
    expect(shows("2+C4=")).toBe("4");
    expect(shows("1/0C7")).toBe("7");
    expect(shows("C")).toBe("0");
  });

  it("works the old click-through test's sums as before", () => {
    expect(shows("12+30=")).toBe("42");
    expect(shows("7*6=")).toBe("42");
    expect(shows("9-12=")).toBe("-3");
    expect(shows("1/4=")).toBe("0.25");
    expect(shows("2.5*2=")).toBe("5");
  });
});
