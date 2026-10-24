// Login rules the server enforces (backend/schemas/user.py,
// backend/services/first_run.py), said the same way on every form.

export const MIN_PASSWORD_LENGTH = 12;
export const PASSWORD_RULE = `At least ${MIN_PASSWORD_LENGTH} characters.`;

/** Whether a new password is shorter than the rule, counted in code points as
 * the server's len() counts them: a character outside the BMP (an emoji such
 * as 🔑) is one, where `.length` says two (#405). */
export function passwordTooShort(password: string): boolean {
  return Array.from(password).length < MIN_PASSWORD_LENGTH;
}

/** GET /api/users/setup-status, read before anyone logs in. */
export interface SetupStatus {
  has_user: boolean;
  is_default: boolean;
  setup_code_required: boolean;
  // The Mac app (its window, or its address in a browser)
  desktop: boolean;
}

const SERVER_SETUP_CODE_HINT =
  "It is printed in the server's log at startup (docker logs <container>) " +
  "and saved as setup-code.txt in the data folder (/data on Docker).";

/** The Mac app this page belongs to: BitcoinTX, or BitcoinTX Beta for a 2.0
 * pre-release (X.Y.Z-beta.N, 2.0 plan 7.4, B10a), with a folder of its own. */
export function macApp(version: string): string {
  return /^\d+\.\d+\.\d+-beta\.[1-9]\d*$/.test(version) ? "BitcoinTX Beta" : "BitcoinTX";
}

// The Mac app never logs it (backend/services/first_run.py)
const MAC_SETUP_CODE_HINT =
  `It is saved as setup-code.txt in ${macApp(__BTCTX_VERSION__)}'s data folder ` +
  `(~/Library/Application Support/${macApp(__BTCTX_VERSION__)}).`;

/** Where the setup code is: the Mac app's data folder, or a server's log
 * and data folder. In a browser at the Mac app's address there's no window
 * to tell, so the server says (`desktop`, #258). */
export function setupCodeHint(desktop: boolean): string {
  return desktop ? MAC_SETUP_CODE_HINT : SERVER_SETUP_CODE_HINT;
}
