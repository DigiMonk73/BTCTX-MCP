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

/**
 * The banner on every page of a pre-release (#670), or null for any other
 * version. On a Mac it is BitcoinTX Preview, an app of its own beside
 * BitcoinTX; on a server (StartOS, Docker) the pre-release is BitcoinTX
 * itself, updated in place or on a volume of its own, so it says nothing of
 * "apart". Until the server has said which (`desktop` unknown), neither.
 */
export function prereleaseBanner(version?: string, desktop?: boolean): { title: string; note: string } | null {
  if (!prereleaseParts(version)) return null;
  if (desktop) return { title: `${macApp(version)} · ${version}`, note: "a test version, apart from your BitcoinTX" };
  return { title: `BitcoinTX · ${version}`, note: desktop === false ? "a test version, not a release" : "a test version" };
}

/** BitcoinTX Preview's line on its first page, where the tester chooses a
 * username and password (#670): its empty ledger isn't their BitcoinTX reset.
 * Null for BitcoinTX itself. */
export function previewFirstPageLine(version?: string): string | null {
  return prereleaseParts(version)
    ? `${macApp(version)} is a separate test app: it starts empty, and BitcoinTX and its ledger are still there, as they were.`
    : null;
}
