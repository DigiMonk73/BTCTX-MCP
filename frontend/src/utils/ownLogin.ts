// The Mac app window's "Choose your username and password" step
// (components/ChooseOwnLogin.tsx): what it checks before sending, and what
// it sends. It keeps the ledger: a login with the default credentials and
// the setup code the window supplies, then a change of them
// (PATCH /api/users/{id}), never reset-account, which deletes every
// transaction.
import api from "../api";
import { PASSWORD_RULE, passwordTooShort } from "./credentials";

// backend/services/first_run.py
const DEFAULT_LOGIN = { username: "admin", password: "password" };

export const NO_SETUP_CODE =
  "BitcoinTX couldn't read its setup code: sign in below with admin / password and the setup code instead.";

/** Why the chosen username and password can't be sent yet, or null. */
export function ownLoginProblem(username: string, password: string, repeat: string): string | null {
  if (!username.trim()) return "Enter a username.";
  if (username.trim().toLowerCase() === DEFAULT_LOGIN.username) {
    return "The username 'admin' is reserved and cannot be used. Please choose a different username.";
  }
  if (passwordTooShort(password)) return `The new password is too short. ${PASSWORD_RULE}`;
  if (password !== repeat) return "The two passwords don't match.";
  return null;
}

/**
 * Replace the default login with the owner's own, keeping every
 * transaction; the session carries on with the new login. When the change
 * fails it logs out again: a reload of the login page would otherwise go
 * on to the Dashboard with the default login still in place.
 */
export async function claimDefaultLogin(username: string, password: string, setupCode: string): Promise<void> {
  await api.post("/login", { ...DEFAULT_LOGIN, setup_code: setupCode });
  try {
    const users = await api.get<{ id: number }[]>("/users/");
    await api.patch(`/users/${users.data[0].id}`, {
      username,
      password,
      current_password: DEFAULT_LOGIN.password,
      setup_code: setupCode,
    });
  } catch (error) {
    await api.post("/logout").catch(() => undefined);
    throw error;
  }
}

/** How long the window may take to read the code before the sign-in form is offered instead. */
export const WINDOW_CODE_WAIT_MS = 5000;

/** The setup code the Mac app's window reads, or null when it can't (no
 * file, a page that isn't the app's, an error, or no answer in time). */
export async function windowSetupCode(
  windowApi: PyWebViewAPI | null, waitMs = WINDOW_CODE_WAIT_MS,
): Promise<string | null> {
  const read = (async () => {
    try {
      return (await windowApi?.setup_code?.()) || null;
    } catch {
      return null;
    }
  })();
  const late = new Promise<null>((resolve) => setTimeout(() => resolve(null), waitMs));
  return Promise.race([read, late]);
}
