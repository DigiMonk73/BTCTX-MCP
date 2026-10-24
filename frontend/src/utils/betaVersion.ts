/**
 * A 2.0 pre-release, VERSION X.Y.Z-beta.N (2.0 plan 7.4, B10a): on a Mac
 * the separate app BitcoinTX Beta, its connector on PyPI as X.Y.ZbN (PEP
 * 440's form). Its release and beta numbers, or null for any other version.
 */
export function betaParts(version?: string): { release: string; beta: string } | null {
  const found = version ? /^(\d+\.\d+\.\d+)-beta\.([1-9]\d*)$/.exec(version) : null;
  return found ? { release: found[1], beta: found[2] } : null;
}
