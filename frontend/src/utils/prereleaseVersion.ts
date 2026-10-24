/**
 * A 2.0 pre-release, VERSION X.Y.Z-alpha.N or X.Y.Z-beta.N (2.0 plan 7.4,
 * B10a; #251's decision 28: alphas first, then betas): on a Mac the separate
 * app BitcoinTX Preview, its connector on PyPI in PEP 440's form, X.Y.ZaN or
 * X.Y.ZbN. Its release number, stage letter and number, or null for any
 * other version.
 */
export function prereleaseParts(version?: string): { release: string; stage: "a" | "b"; n: string } | null {
  const found = version ? /^(\d+\.\d+\.\d+)-(alpha|beta)\.([1-9]\d*)$/.exec(version) : null;
  return found ? { release: found[1], stage: found[2] === "alpha" ? "a" : "b", n: found[3] } : null;
}

/** The Mac app a version belongs to: BitcoinTX, or BitcoinTX Preview for a 2.0
 * pre-release, with a folder of its own. */
export function macApp(version?: string): string {
  return prereleaseParts(version) ? "BitcoinTX Preview" : "BitcoinTX";
}
