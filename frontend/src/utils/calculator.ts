// The sidebar calculator's keys, worked as a pocket calculator works them
// (#450): left to right, the running total kept through a chain of
// operations. The sums are worked out exactly in decimals, as BitcoinTX's
// own figures are, never in a computer's binary numbers (0.1 + 0.2 =
// 0.30000000000000004 there), and each result is rounded to what the
// display holds.

export type Operator = "+" | "-" | "*" | "/";

export interface CalculatorState {
  /** What the display shows: the number being typed, a result, or ERROR. */
  display: string;
  /** The left side and the operator waiting for the number after it. */
  pending: { left: string; operator: Operator } | null;
  /** The next digit starts a new number instead of joining the display's. */
  startsNew: boolean;
}

/** Shown for a division by zero, or a result too long for the display. */
export const ERROR = "Error";

export const CLEARED: CalculatorState = { display: "0", pending: null, startsNew: false };

const OPERATORS: readonly Operator[] = ["+", "-", "*", "/"];

// What the display holds, so that no number on it is longer than 17
// characters ("-0.00000000000001", "-9999999999999999"): a number is typed
// with 15 digits at most, as on a 15-digit pocket calculator; a result's
// decimals are rounded to 15 significant digits, and to 14 decimals at most
// (six past a sat's eight); a result of more than 16 whole digits is ERROR.
const SIGNIFICANT_DIGITS = 15;
const MAX_DECIMALS = 14;
const MAX_WHOLE_DIGITS = 16;

/** A decimal number exactly: units / 10^scale. */
interface Decimal { units: bigint; scale: number }

export function isOperator(key: string): key is Operator {
  return (OPERATORS as readonly string[]).includes(key);
}

/** The calculator after one key: a digit, ".", an operator, "=" or "C". */
export function pressKey(state: CalculatorState, key: string): CalculatorState {
  if (key === "C") return CLEARED;
  if (key === "=") return equals(state);
  if (isOperator(key)) return chain(state, key);
  return typeKey(state, key);
}

function typeKey(state: CalculatorState, key: string): CalculatorState {
  const typed = state.startsNew ? "0" : state.display;
  if (key === ".") {
    return typed.includes(".") ? state : { ...state, display: typed + ".", startsNew: false };
  }
  if (typed === "0") return { ...state, display: key, startsNew: false };
  if (typed.replace(/\D/g, "").length >= SIGNIFICANT_DIGITS) return state;
  return { ...state, display: typed + key, startsNew: false };
}

function chain(state: CalculatorState, operator: Operator): CalculatorState {
  if (state.display === ERROR) return state;
  // An operator right after another replaces it: `5 + + 1` is 5 + 1.
  if (state.pending && state.startsNew) {
    return { ...state, pending: { ...state.pending, operator } };
  }
  // A pending operation is worked out first, and its result is the new
  // left side: `2 + 3 + 4` shows 5 at the second +.
  const left = state.pending ? workedOut(state.pending, state.display) : state.display;
  if (left === ERROR) return { display: ERROR, pending: null, startsNew: true };
  return { display: left, pending: { left, operator }, startsNew: true };
}

function equals(state: CalculatorState): CalculatorState {
  // With no number typed after the operator (`5 + =`), the operator is dropped.
  const display = state.pending && !state.startsNew
    ? workedOut(state.pending, state.display) : state.display;
  return { display, pending: null, startsNew: true };
}

// The exact result as a fraction (numerator, positive denominator), then
// rounded for the display.
function workedOut(pending: { left: string; operator: Operator }, right: string): string {
  const a = decimal(pending.left);
  const b = decimal(right);
  if (pending.operator === "/") {
    if (b.units === 0n) return ERROR;
    // (a.units / 10^a.scale) / (b.units / 10^b.scale)
    const sign = b.units < 0n ? -1n : 1n;
    return rounded(sign * a.units * 10n ** BigInt(b.scale), sign * b.units * 10n ** BigInt(a.scale));
  }
  if (pending.operator === "*") {
    return rounded(a.units * b.units, 10n ** BigInt(a.scale + b.scale));
  }
  const scale = Math.max(a.scale, b.scale);
  const x = a.units * 10n ** BigInt(scale - a.scale);
  const y = b.units * 10n ** BigInt(scale - b.scale);
  return rounded(pending.operator === "+" ? x + y : x - y, 10n ** BigInt(scale));
}

function decimal(number: string): Decimal {
  const [whole, fraction = ""] = number.split(".");
  return { units: BigInt(whole + fraction), scale: fraction.length };
}

// numerator / denominator (above 0) rounded half away from zero to the
// decimals that fit the display, written out in full (0.00000005, never
// 5e-8, as #101 has it for the rest of BitcoinTX), or ERROR when its whole
// number is too long.
function rounded(numerator: bigint, denominator: bigint): string {
  const size = numerator < 0n ? -numerator : numerator;
  if (size === 0n) return "0";
  const decimals = Math.max(0, Math.min(
    MAX_DECIMALS, SIGNIFICANT_DIGITS - 1 - magnitude(size, denominator)));
  const scaled = size * 10n ** BigInt(decimals);
  let units = scaled / denominator;
  if (2n * (scaled % denominator) >= denominator) units += 1n;
  if (units === 0n) return "0";
  const digits = units.toString().padStart(decimals + 1, "0");
  const whole = digits.slice(0, digits.length - decimals);
  if (whole.length > MAX_WHOLE_DIGITS) return ERROR;
  const fraction = digits.slice(whole.length).replace(/0+$/, "");
  return `${numerator < 0n ? "-" : ""}${whole}${fraction ? `.${fraction}` : ""}`;
}

// The power of ten of a fraction's first significant digit: 2 for 123.4,
// -3 for 0.0012.
function magnitude(numerator: bigint, denominator: bigint): number {
  const guess = numerator.toString().length - denominator.toString().length;
  const reaches = guess >= 0
    ? numerator >= denominator * 10n ** BigInt(guess)
    : numerator * 10n ** BigInt(-guess) >= denominator;
  return reaches ? guess : guess - 1;
}
