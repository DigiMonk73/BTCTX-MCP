// Login rules the server enforces (backend/schemas/user.py,
// backend/services/first_run.py), said the same way on every form.

export const MIN_PASSWORD_LENGTH = 12;
export const PASSWORD_RULE = `At least ${MIN_PASSWORD_LENGTH} characters.`;

/** Whether a new password is shorter than the rule, its characters counted
 * as the server counts them: an emoji is one, where `.length` says two (#405). */
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

// The Mac app never logs it (backend/services/first_run.py)
const MAC_SETUP_CODE_HINT =
  "It is saved as setup-code.txt in BitcoinTX's data folder (~/Library/Application Support/BitcoinTX).";

/** Where the setup code is: the Mac app's data folder, or a server's log
 * and data folder. In a browser at the Mac app's address there's no window
 * to tell, so the server says (`desktop`, #258). */
export function setupCodeHint(desktop: boolean): string {
  return desktop ? MAC_SETUP_CODE_HINT : SERVER_SETUP_CODE_HINT;
}
