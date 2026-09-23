import { FileHelper, z } from '@start9labs/start-sdk'
import { sdk } from '../sdk'

const shape = z.object({
  // The password this package generated at install or on Reset Login
  // Credentials. BitcoinTX owns the live credential: a password changed in the
  // app is not reflected here.
  adminPassword: z.string().optional().catch(undefined),
})

/** Package state, on the `startos` volume that no subcontainer mounts. */
export const storeJson = FileHelper.json(
  { base: sdk.volumes.startos, subpath: 'store.json' },
  shape,
)
