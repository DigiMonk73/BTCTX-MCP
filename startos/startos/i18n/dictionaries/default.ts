export const DEFAULT_LANG = 'en_US'

const dict = {
  // actions/resetCredentials.ts
  'Reset Login Credentials': 0,
  'Set the username back to "admin" and generate a new random password. Use this if you are locked out.': 1,
  'This replaces your current username and password. Your transactions are not touched.': 2,
  'Credentials Reset': 3,
  'Log in to BitcoinTX with these. Show Credentials displays them again later.': 4,

  // actions/showCredentials.ts
  'Show Credentials': 5,
  'The username and password for logging in to BitcoinTX.': 6,
  'Login Credentials': 7,
  'Log in to BitcoinTX with these. If you changed the password inside BitcoinTX, use that one instead; run Reset Login Credentials if you have lost it.': 8,
  'This install predates generated passwords, so the original default login is shown. If you changed it inside BitcoinTX, use yours; run Reset Login Credentials if you have lost it.': 9,

  // init/installCredentials.ts
  'Creating the BitcoinTX database': 10,
  'Copy your BitcoinTX login before starting the service': 11,

  // interfaces.ts
  'Web UI': 12,
  'The BitcoinTX web interface': 13,

  // main.ts
  'Starting BitcoinTX': 14,
  'Web Interface': 15,
  'BitcoinTX is ready': 16,
  'BitcoinTX is not responding': 17,

  // utils.ts
  Username: 18,
  Password: 19,
} as const

/**
 * Plumbing. DO NOT EDIT.
 */
export type I18nKey = keyof typeof dict
export type LangDict = Record<(typeof dict)[I18nKey], string>
export default dict
