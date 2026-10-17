import { T } from '@start9labs/start-sdk'
import { i18n } from './i18n'
import { currentChoice, priceEnv } from './priceSource'
import { sdk } from './sdk'
import {
  APP_USER,
  OWN_DATA,
  appEnv,
  asAppUser,
  mainMounts,
  uiPort,
} from './utils'

/** GET /api/health: 200 only when the database answers at the current schema. */
async function appHealth(): Promise<Omit<T.NamedHealthCheckResult, 'name'>> {
  let res: Response
  try {
    res = await fetch(`http://127.0.0.1:${uiPort}/api/health`, {
      signal: AbortSignal.timeout(5000),
    })
  } catch {
    return { result: 'failure', message: i18n('BitcoinTX is not responding') }
  }
  if (res.ok) return { result: 'success', message: i18n('BitcoinTX is ready') }
  const body = (await res.json().catch(() => ({}))) as { detail?: string }
  return {
    result: 'failure',
    message: i18n('The database is not ready: ${detail}', {
      detail: body.detail ?? `HTTP ${res.status}`,
    }),
  }
}

export const main = sdk.setupMain(async ({ effects }) => {
  console.info(i18n('Starting BitcoinTX'))

  // The Price Source & Privacy choice, with the bridge addresses of Mempool
  // and Tor: a change to either restarts the service with the new settings.
  const env = {
    ...appEnv,
    ...(await priceEnv(effects, await currentChoice(effects, true), true)),
  }

  const app = sdk.SubContainer.of(
    effects,
    { imageId: 'main' },
    mainMounts(),
    'btctx',
  )

  return (
    sdk.Daemons.of(effects)
      // The volume to the app's user at every start (main.md, "Oneshots"):
      // StartOS mounts it root-owned, and before 1.2.9 the app ran as root.
      .addOneshot('chown', {
        subcontainer: app,
        exec: { command: OWN_DATA, user: 'root' },
        requires: [],
      })
      // Schema upgrade (with a copy of the database in /data/backups first)
      // as its own step, before the web server.
      .addOneshot('migrate', {
        subcontainer: app,
        exec: {
          command: ['python', '-m', 'backend.cli', 'migrate'],
          cwd: '/app',
          env,
          user: APP_USER,
        },
        requires: ['chown'],
      })
      .addDaemon('webui', {
        subcontainer: app,
        exec: {
          // From root to the app's user, keeping the right to open port 80
          command: asAppUser([
            'uvicorn',
            'backend.main:app',
            '--host',
            '0.0.0.0',
            '--port',
            String(uiPort),
            // Request lines carry client addresses and dates (?date=...)
            '--no-access-log',
            // No "server: uvicorn" header on the responses
            '--no-server-header',
          ]),
          cwd: '/app',
          env,
          user: 'root',
        },
        ready: {
          display: i18n('Web Interface'),
          gracePeriod: 30_000,
          fn: appHealth,
        },
        requires: ['migrate'],
      })
  )
})
