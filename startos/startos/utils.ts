import { T, utils } from '@start9labs/start-sdk'
import { storeJson } from './fileModels/store.json'
import { currentChoice, priceEnv } from './priceSource'
import { sdk } from './sdk'

export const uiPort = 80
export const ADMIN_USERNAME = 'admin'

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
 * subcontainer on the app's volume, through the image's start-up script as at
 * every start (main.ts): it runs the command as the app's user, giving it the
 * volume first when needed, since an action or init may run before the first
 * start after an update or a restore. Every command migrates the database
 * first, so this works on an empty volume. Throws on a non-zero exit.
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
      // The image's ENTRYPOINT (the Dockerfile), as root, the image's user:
      // execFail takes no sdk.useEntrypoint()
      const res = await sub.execFail(
        ['docker-entrypoint.sh', 'python', '-m', 'backend.cli', ...args],
        { env, input: opts.input, timeout: 10 * 60_000 },
      )
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
