// The sidebar calculator's keys, worked as a pocket calculator works them
// (#450): left to right, the running total kept through a chain of
// operations, each result rounded to the digits its numbers can carry.

export type Operator = "+" | "-" | "*" | "/";

export interface CalculatorState {
  /** What the display shows: the number being typed, a result, or ERROR. */
  display: string;
  /** The left side and the operator waiting for the number after it. */
  pending: { left: string; operator: Operator } | null;
  /** The next digit starts a new number instead of joining the display's. */
  startsNew: boolean;
}

/** Shown for a result that isn't a number: a division by zero, an overflow. */
export const ERROR = "Error";

export const CLEARED: CalculatorState = { display: "0", pending: null, startsNew: false };

export const OPERATORS: readonly string[] = ["+", "-", "*", "/"];

// A double carries 15 significant digits reliably; past them is rounding
// noise (0.1 + 0.2 = 0.30000000000000004).
const SIGNIFICANT_DIGITS = 15;

// Decimals a result is written with at most, twice a sat's eight: the
// sidebar's display holds about 21 characters.
const MAX_DECIMALS = 16;

/** The calculator after one key: a digit, ".", an operator, "=" or "C". */
export function pressKey(state: CalculatorState, key: string): CalculatorState {
  if (key === "C") return CLEARED;
  if (key === "=") return equals(state);
  if (OPERATORS.includes(key)) return chain(state, key as Operator);
  return typeKey(state, key);
}

function typeKey(state: CalculatorState, key: string): CalculatorState {
  const typed = state.startsNew ? "0" : state.display;
  if (key === "." && typed.includes(".")) return state;
  const display = typed === "0" && key !== "." ? key : typed + key;
  return { ...state, display, startsNew: false };
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

function workedOut(pending: { left: string; operator: Operator }, right: string): string {
  const a = Number(pending.left);
  const b = Number(right);
  const results = { "+": a + b, "-": a - b, "*": a * b, "/": a / b };
  const result = results[pending.operator];
  if (!Number.isFinite(result)) return ERROR;
  return written(result, exactDecimals(pending.left, right, pending.operator));
}

// How many decimals the exact result has: a sum or difference has as many
// as its longer number, a product as many as both together, and a
// quotient may have no end.
function exactDecimals(left: string, right: string, operator: Operator): number {
  if (operator === "/") return MAX_DECIMALS;
  const decimals = [decimalsOf(left), decimalsOf(right)];
  return operator === "*" ? decimals[0] + decimals[1] : Math.max(...decimals);
}

function decimalsOf(number: string): number {
  return number.match(/\.(\d+)/)?.[1].length ?? 0;
}

// The result rounded to its exact decimals, at most SIGNIFICANT_DIGITS in
// all, and written out in full (0.00000005, never 5e-8, as #101 has it for
// the rest of BitcoinTX).
function written(result: number, exact: number): string {
  const significant = result === 0
    ? 0 : SIGNIFICANT_DIGITS - 1 - Math.floor(Math.log10(Math.abs(result)));
  const decimals = Math.max(0, Math.min(exact, significant, MAX_DECIMALS));
  const text = result.toFixed(decimals);
  const trimmed = text.includes(".") ? text.replace(/\.?0+$/, "") : text;
  return Number(trimmed) === 0 ? "0" : trimmed;
}
