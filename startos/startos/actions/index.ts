import { sdk } from '../sdk'
import { resetCredentials } from './resetCredentials'
import { showCredentials } from './showCredentials'

export const actions = sdk.Actions.of()
  .addAction(showCredentials)
  .addAction(resetCredentials)
