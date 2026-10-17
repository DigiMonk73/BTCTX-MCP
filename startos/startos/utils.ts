import { T, utils } from '@start9labs/start-sdk'
import { storeJson } from './fileModels/store.json'
import { currentChoice, priceEnv } from './priceSource'
import { sdk } from './sdk'

export const uiPort = 80
export const ADMIN_USERNAME = 'admin'

/**
 * The image's own user (the Dockerfile's `btctx`, uid 10001): BitcoinTX
 * never runs as root (#202). Volumes from before 1.2.9 are root's.
 */
export const APP_USER = 'btctx'

/** Gives the `main` volume to the app's user; run as root (main.md, "Oneshots"). */
export const OWN_DATA: [string, ...string[]] = [
  'chown',
  '-R',
  `${APP_USER}:${APP_USER}`,
  '/data',
]

/**
 * Runs `command` as the app's user from root, keeping one right: to open
 * port 80, which an ordinary user may not in StartOS's container
 * (net.ipv4.ip_unprivileged_port_start is 1024 there). The image's
 * docker-entrypoint.sh drops to it the same way.
 */
export function asAppUser(
  command: [string, ...string[]],
): [string, ...string[]] {
  return [
    'setpriv',
    `--reuid=${APP_USER}`,
    `--regid=${APP_USER}`,
    '--init-groups',
    '--inh-caps=-all,+net_bind_service',
    '--ambient-caps=-all,+net_bind_service',
    '--no-new-privs',
    '--',
    ...command,
  ]
}

/** Environment for every process that runs BitcoinTX code. */
export const appEnv = {
  DATABASE_FILE: '/data/btctx.db',
  LOG_LEVEL: 'INFO',
  // Where BitcoinTX runs: its words name StartOS's action (#145)
  BTCTX_HOST: 'startos',
}

/** The `main` volume at /data, as the app expects it. */
export function mainMounts() {
  return sdk.Mounts.of().mountVolume({
    volumeId: 'main',
    subpath: null,
    mountpoint: '/data',
    readonly: false,
  })
}

/**
 * For a migration whose calculation fixes reach existing transactions only
 * through a recalculation: Recalculate Ledger becomes due, and the next init
 * asks for it once (init/recalculateTask.ts).
 */
export async function makeRecalculationDue(effects: T.Effects) {
  await storeJson.merge(effects, {
    recalculateLedger: true,
    recalculateAsked: false,
  })
}

export function generatePassword(): string {
  return utils.getDefaultString({ charset: 'a-z,A-Z,0-9', len: 24 })
}

/**
 * Run `python -m backend.cli <args>` (backend/cli.py) in a temporary
 * subcontainer on the app's volume, as the app's user: the volume is given to
 * it first, as at every start, since an action or init may run before the
 * first start after an update or a restore. Every command migrates the
 * database first, so this works on an empty volume. Throws on a non-zero exit.
 * `prices`: pass the Price Source & Privacy choice, for a command that may
 * look up a price.
 */
export async function runAppCli(
  effects: T.Effects,
  args: string[],
  opts: { input?: string; prices?: boolean } = {},
): Promise<string> {
  const env = opts.prices
    ? {
        ...appEnv,
        ...(await priceEnv(
          effects,
          await currentChoice(effects, false),
          false,
        )),
      }
    : appEnv
  return sdk.SubContainer.withTemp(
    effects,
    { imageId: 'main' },
    mainMounts(),
    `cli-${args[0]}`,
    async (sub) => {
      await sub.execFail(OWN_DATA, { user: 'root', timeout: 10 * 60_000 })
      const res = await sub.execFail(['python', '-m', 'backend.cli', ...args], {
        cwd: '/app',
        env,
        user: APP_USER,
        input: opts.input,
        timeout: 10 * 60_000,
      })
      return res.stdout.toString()
    },
  )
}

/** Set the app's login to admin / `password`, through the app's own hashing. */
export async function setAppCredentials(
  effects: T.Effects,
  password: string,
): Promise<void> {
  await runAppCli(
    effects,
    ['set-password', '--username', ADMIN_USERNAME, '--password-stdin'],
    { input: `${password}\n` },
  )
}

/**
 * Give a login still on the app's shipped default (admin / password) this
 * password. True if it was the default (and now isn't).
 */
export async function replaceDefaultLogin(
  effects: T.Effects,
  password: string,
): Promise<boolean> {
  const out = await runAppCli(
    effects,
    ['set-password', '--if-default', '--password-stdin'],
    { input: `${password}\n` },
  )
  return out.includes('Password set for user')
}
