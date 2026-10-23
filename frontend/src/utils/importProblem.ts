// An import preview's error or warning, as its list says it.

/** "Row 4 (amount): Amount must be positive.", the column only when given
 * one; an error about the whole file (the server's row 0) alone, since it
 * is no row's (#534). */
export function problemText(problem: { row_number: number; message: string }, column?: string | null): string {
  if (problem.row_number <= 0) return problem.message;
  return `Row ${problem.row_number}${column ? ` (${column})` : ""}: ${problem.message}`;
}
