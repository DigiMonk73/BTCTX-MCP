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
}

export const PRICE_SOURCES: { value: PriceSource; label: string; help: string }[] = [
  {
    value: "mempool",
    label: "My mempool server",
    help:
      "Your own node answers: the live price, the block height and past prices. Nothing goes to a " +
      "public site. Its past prices start when it was installed; for older days, turn on the " +
      "fallback to public sites (Settings) or type the value in.",
  },
  {
    value: "public",
    label: "Public price sites",
    help:
      "The live price from CoinGecko or Kraken, the block height from Blockchain.info or " +
      "Blockstream. Past prices come from one download of the whole daily history (Bitstamp), " +
      "the same for every install, so your transaction dates are never sent. The sites see your " +
      "IP address; a VPN, or a Tor proxy set in Settings, hides it.",
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
