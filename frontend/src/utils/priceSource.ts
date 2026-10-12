/**
 * Where BitcoinTX gets Bitcoin prices and the block height
 * (backend/services/outbound.py), as the price card shows it
 * (components/priceCard/PriceSourceCard.tsx): the first-run question on the
 * Dashboard, Settings → Privacy & network, and read-only when the server
 * sets it. One set of words everywhere (#145).
 */

export type PriceSource = "off" | "public" | "mempool";
export type Host = "mac" | "startos" | "server";

export interface NetworkSettingsData {
  /** "unset": a fresh install before the owner chose. */
  price_source: PriceSource | "unset";
  mempool_url: string | null;
  mempool_fallback: boolean;
  proxy_url: string | null;
  /** Set by the server (StartOS: the Price Source & Privacy action), read-only here. */
  managed?: boolean;
  /** The server's settings are invalid: nothing is asked. */
  invalid?: boolean;
  /** Where BitcoinTX runs: the Mac app, StartOS, or another server (Docker, source). */
  host?: Host;
}

export interface PriceChoice {
  value: PriceSource;
  label: string;
  help: string;
}

/** Most private first. Nothing is ever preselected: the owner picks. */
export const PRICE_CHOICES: PriceChoice[] = [
  {
    value: "mempool",
    label: "My own Mempool",
    help: "Most private, if you run Mempool on your own node. Hourly.",
  },
  {
    value: "public",
    label: "Public price sites",
    help:
      "Bitstamp and Kraken for prices; Blockchain.info, Blockstream or mempool.space for the block " +
      "height. They see your IP address and when BitcoinTX is open, never your dates.",
  },
  {
    value: "off",
    label: "Nobody",
    help: "Fully offline. Type newer values yourself.",
  },
];

export const MEMPOOL_PLACEHOLDER = "http://umbrel.local:3006";
export const TOR_PLACEHOLDER = "socks5h://127.0.0.1:9050";
export const FOOTER =
  "Your ledger is never sent anywhere. A value you type always wins, and a stored price never changes.";

/** The card as the owner is filling it in. */
export interface PriceForm {
  source: PriceSource | "";
  mempoolUrl: string;
  backup: boolean;
  tor: boolean;
  torUrl: string;
}

export function isOnion(url: string): boolean {
  try {
    return new URL(url.trim()).hostname.endsWith(".onion");
  } catch {
    return false;
  }
}

/** The form for saved settings. "Through Tor" is the proxy: any proxy works. */
export function formFromSettings(s: NetworkSettingsData): PriceForm {
  return {
    source: s.price_source === "unset" ? "" : s.price_source,
    mempoolUrl: s.mempool_url ?? "",
    backup: s.mempool_fallback,
    tor: Boolean(s.proxy_url),
    torUrl: s.proxy_url ?? TOR_PLACEHOLDER,
  };
}

/** Whether "Through Tor" is offered for the form as it is: for public
 * sites, for your Mempool's backup, and for an .onion Mempool. */
export function torOffered(f: PriceForm): boolean {
  return f.source === "public" || (f.source === "mempool" && (f.backup || isOnion(f.mempoolUrl)));
}

/** What PUT /api/settings/network gets. An address or proxy not in use is
 * kept, so it comes back when the owner switches back. */
export function payloadFromForm(f: PriceForm) {
  const onion = f.source === "mempool" && isOnion(f.mempoolUrl);
  return {
    price_source: f.source,
    mempool_url: f.mempoolUrl.trim() || null,
    mempool_fallback: f.backup,
    proxy_url: (f.tor || onion) && f.torUrl.trim() ? f.torUrl.trim() : null,
  };
}

/** Whether the form differs from the saved settings (addresses compared
 * without surrounding spaces). Nothing to save until a source is chosen. */
export function priceFormChanged(saved: NetworkSettingsData | null, f: PriceForm): boolean {
  if (saved === null || f.source === "") return false;
  const p = payloadFromForm(f);
  return (
    p.price_source !== saved.price_source ||
    p.mempool_url !== (saved.mempool_url ?? null) ||
    p.mempool_fallback !== saved.mempool_fallback ||
    p.proxy_url !== (saved.proxy_url ?? null)
  );
}

/** Why the button is off, if it is: nothing chosen, or a Mempool without an address. */
export function cannotSave(f: PriceForm): string | null {
  if (f.source === "") return "Choose one of the three.";
  if (f.source === "mempool" && !f.mempoolUrl.trim()) return "Enter your Mempool's address.";
  // Review of #180: ticked with no address would have asked the sites directly
  if (f.tor && torOffered(f) && !f.torUrl.trim()) return "Enter Tor's address.";
  if (payloadFromForm(f).proxy_url === null && f.source === "mempool" && isOnion(f.mempoolUrl)) {
    return "An .onion address is reached through Tor: enter Tor's address.";
  }
  return null;
}

/** The read-only banner when the server sets the choice, or null. */
export function managedBanner(s: NetworkSettingsData): string | null {
  if (!s.managed) return null;
  if (s.host === "startos") {
    return "Set in StartOS. To change it: BitcoinTX › Actions › Price Source & Privacy.";
  }
  return "Set by this server's settings (BTCTX_PRICE_SOURCE), so it can't be changed here.";
}

/** How a server-set address reads: StartOS's internal ones aren't for people. */
export function shownAddress(s: NetworkSettingsData, what: "mempool" | "tor"): string | null {
  const url = what === "mempool" ? s.mempool_url : s.proxy_url;
  if (s.managed && s.host === "startos") {
    if (what === "mempool") return url ? "Mempool on this server" : "Mempool isn't installed on this server yet";
    return url ? "Tor on this server" : null;
  }
  return url;
}
