import { T } from '@start9labs/start-sdk'
import { PriceSource, storeJson } from './fileModels/store.json'
import { sdk } from './sdk'

// The optional dependencies (manifest `dependencies`), reached over the
// StartOS bridge (10.0.3.1:<assigned port>, plain http inside the server):
// no certificate, no LAN address that can change.
export const MEMPOOL = { packageId: 'mempool', hostId: 'main', port: 8080 }
export const TOR = { packageId: 'tor', hostId: 'socks', port: 9050 }

export interface PriceChoice {
  source: PriceSource
  fallback: boolean
  tor: boolean
}

/** The Price Source & Privacy choice in store.json ('unset' until made). */
export function readChoice(s: {
  priceSource?: PriceSource
  mempoolFallback?: boolean
  useTor?: boolean
}): PriceChoice {
  return {
    source: s.priceSource ?? 'unset',
    fallback: s.mempoolFallback ?? false,
    tor: s.useTor ?? false,
  }
}

/** Whether BitcoinTX may ask public price sites with this choice. */
export function asksPublicSites(c: PriceChoice): boolean {
  return c.source === 'public' || (c.source === 'mempool' && c.fallback)
}

/** The store's choice; `watch` restarts the caller when it changes. */
export async function currentChoice(
  effects: T.Effects,
  watch: boolean,
): Promise<PriceChoice> {
  const read = storeJson.read((s) => readChoice(s))
  return (
    (watch ? await read.const(effects) : await read.once()) ?? readChoice({})
  )
}

/**
 * The app's price settings for this choice (backend/services/outbound.py
 * reads BTCTX_PRICE_SOURCE and co.). Nothing for 'unset': the app's own
 * Settings decide. `watch` (main): re-run when an address changes, e.g. once
 * Mempool is installed. Mempool's address is empty while it's missing (the
 * app then says so); Tor's falls back to its fixed port, so requests fail
 * rather than go out directly.
 */
export async function priceEnv(
  effects: T.Effects,
  choice: PriceChoice,
  watch: boolean,
): Promise<Record<string, string>> {
  if (choice.source === 'unset') return {}
  const env: Record<string, string> = {
    BTCTX_PRICE_SOURCE: choice.source,
    BTCTX_MEMPOOL_FALLBACK: choice.fallback ? 'on' : 'off',
    BTCTX_MEMPOOL_URL: '',
    BTCTX_PROXY_URL: '',
  }
  if (choice.source === 'mempool') {
    const mempool = sdk.host.getBridgeAddress(effects, {
      packageId: MEMPOOL.packageId,
      hostId: MEMPOOL.hostId,
      internalPort: MEMPOOL.port,
      ssl: false,
    })
    const address = watch ? await mempool.const() : await mempool.once()
    env.BTCTX_MEMPOOL_URL = address ? `http://${address}` : ''
  }
  if (choice.tor && asksPublicSites(choice)) {
    const socks = sdk.host.getBridgeAddress(effects, {
      packageId: TOR.packageId,
      hostId: TOR.hostId,
      internalPort: TOR.port,
      fallbackPort: TOR.port,
    })
    env.BTCTX_PROXY_URL = `socks5h://${watch ? await socks.const() : await socks.once()}`
  }
  return env
}
