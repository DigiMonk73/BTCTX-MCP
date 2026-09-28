import { showCredentials } from '../actions/showCredentials'
import { storeJson } from '../fileModels/store.json'
import { i18n } from '../i18n'
import { sdk } from '../sdk'
import { generatePassword, replaceDefaultLogin } from '../utils'

/**
 * Once after an update (or restore) from before 1.2.0: installs from before
 * generated passwords may still have the app's default login, which BitcoinTX
 * 1.1.0 and later accept only with the setup code from the service log.
 * Replace it with a generated password and make collecting it the first step.
 */
export const defaultLogin = sdk.setupOnInit(async (effects) => {
  const check = await storeJson.read((s) => s.checkDefaultLogin).once()
  if (!check) return
  const password = generatePassword()
  // The app first, so the store never shows a password that doesn't work.
  if (await replaceDefaultLogin(effects, password)) {
    await storeJson.merge(effects, { adminPassword: password })
    await sdk.action.createOwnTask(effects, showCredentials, 'critical', {
      reason: i18n(
        'Your BitcoinTX login was still the original admin / password, so it now has a generated password. Copy it before starting the service.',
      ),
    })
  }
  await storeJson.merge(effects, { checkDefaultLogin: false })
})
