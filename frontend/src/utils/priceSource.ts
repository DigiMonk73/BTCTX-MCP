/**
 * Where BitcoinTX gets Bitcoin prices and the block height
 * (backend/services/outbound.py). Shared by Settings → Privacy & network and
 * the one-time question after the first login.
 */

export type PriceSource = "off" | "public" | "mempool";

export interface NetworkSettingsData {
  /** "unset": a fresh install before the owner chose. */
  price_source: PriceSource | "unset";
  mempool_url: string | null;
  mempool_fallback: boolean;
  proxy_url: string | null;
  /** Set by the server (StartOS: the Price Source & Privacy action), read-only here. */
  managed?: boolean;
}

export const MANAGED_NOTE =
  "Set by your server: on StartOS, change them with the Price Source & Privacy action on " +
  "BitcoinTX's service page.";

export const PRICE_SOURCES: { value: PriceSource; label: string; help: string }[] = [
  {
    value: "mempool",
    label: "My mempool server",
    help:
      "Your own node answers: the live price, the block height and past prices. Nothing goes to a " +
      "public site. Its past prices start when it was installed; for older days, turn on the " +
      "fallback to public sites (Settings) or type the value in. Mempool on the same StartOS " +
      "server: use its Price Source & Privacy action instead.",
  },
  {
    value: "public",
    label: "Public price sites",
    help:
      "The live price from Kraken (CoinGecko if Kraken fails), the block height from " +
      "Blockchain.info (else Blockstream or mempool.space). Past prices come from one download of " +
      "the whole daily history (Bitstamp, else Coinbase), the same for every install, then only " +
      "the latest days (Bitstamp, Kraken or Coinbase), so your transaction dates are never sent. " +
      "These sites see your IP address and when BitcoinTX is open (it asks for the price every " +
      "2 minutes while a page is showing); a VPN, or a Tor proxy set in Settings, hides the IP address.",
  },
  {
    value: "off",
    label: "Off",
    help:
      "Nothing is contacted. Prices already stored still work; for anything else you type the " +
      "USD value yourself.",
  },
];

export const MEMPOOL_PLACEHOLDER = "http://umbrel.local:3006";

/** The Privacy & network form as the owner is filling it in. */
export interface NetworkSettingsForm {
  source: PriceSource | "";
  mempoolUrl: string;
  fallback: boolean;
  proxyUrl: string;
}

/** Whether the form differs from the saved settings (addresses compared
 * without surrounding spaces). Nothing to save until a source is chosen. */
export function networkSettingsChanged(saved: NetworkSettingsData | null, form: NetworkSettingsForm): boolean {
  return (
    saved !== null &&
    form.source !== "" &&
    (form.source !== saved.price_source ||
      form.mempoolUrl.trim() !== (saved.mempool_url ?? "") ||
      form.fallback !== saved.mempool_fallback ||
      form.proxyUrl.trim() !== (saved.proxy_url ?? ""))
  );
}
