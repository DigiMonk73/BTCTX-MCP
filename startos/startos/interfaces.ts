import { i18n } from './i18n'
import { sdk } from './sdk'
import { uiPort } from './utils'

// Host and interface ids are unchanged since 0.3.x: renaming them would drop
// the domains and Tor addresses users attached to them.
export const hostId = 'ui-multi'
export const webUiInterfaceId = 'webui'

export const setInterfaces = sdk.setupInterfaces(async ({ effects }) => {
  const origin = await sdk.MultiHost.of(effects, hostId).bindPort(uiPort, {
    protocol: 'http',
  })

  const ui = sdk.createInterface(effects, {
    name: i18n('Web UI'),
    id: webUiInterfaceId,
    description: i18n('The BitcoinTX web interface'),
    type: 'ui',
    masked: false,
    schemeOverride: null,
    username: null,
    path: '',
    query: {},
  })

  return [await origin.export([ui])]
})
