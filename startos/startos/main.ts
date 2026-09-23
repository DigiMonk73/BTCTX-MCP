import { i18n } from './i18n'
import { sdk } from './sdk'
import { appEnv, mainMounts, uiPort } from './utils'

export const main = sdk.setupMain(async ({ effects }) => {
  console.info(i18n('Starting BitcoinTX'))

  return sdk.Daemons.of(effects).addDaemon('webui', {
    subcontainer: sdk.SubContainer.of(
      effects,
      { imageId: 'main' },
      mainMounts(),
      'btctx',
    ),
    exec: {
      command: [
        'uvicorn',
        'backend.main:app',
        '--host',
        '0.0.0.0',
        '--port',
        String(uiPort),
      ],
      env: appEnv,
    },
    ready: {
      display: i18n('Web Interface'),
      fn: () =>
        sdk.healthCheck.checkWebUrl(effects, `http://localhost:${uiPort}`, {
          timeout: 5000,
          successMessage: i18n('BitcoinTX is ready'),
          errorMessage: i18n('BitcoinTX is not responding'),
        }),
    },
    requires: [],
  })
})
