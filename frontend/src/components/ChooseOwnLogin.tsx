import React, { useState } from "react";
import { extractErrorMessage } from "../utils/apiError";
import { PASSWORD_RULE } from "../utils/credentials";
import { claimDefaultLogin, ownLoginProblem, windowSetupCode } from "../utils/ownLogin";

interface ChooseOwnLoginProps {
  /** The Mac app window's API: it reads the setup code (desktop/desktop_api.py). */
  windowApi: PyWebViewAPI;
  /** On into the app, as a first login goes. */
  onDone: () => Promise<void>;
  /** The window couldn't read the code: back to the sign-in form, with its Setup Code field. */
  onNoCode: () => void;
}

/**
 * The login card in the Mac app's window while the account still has the
 * default login (a first start, or an older install never changed): the
 * owner chooses a username and password, the window supplies the setup
 * code, and every transaction is kept (utils/ownLogin.ts).
 */
const ChooseOwnLogin: React.FC<ChooseOwnLoginProps> = ({ windowApi, onDone, onNoCode }) => {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [repeat, setRepeat] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const problem = ownLoginProblem(username, password, repeat);
    setErrorMsg(problem ?? "");
    if (problem) return;
    setIsSubmitting(true);
    const code = await windowSetupCode(windowApi);
    if (!code) {
      setIsSubmitting(false);
      onNoCode();
      return;
    }
    try {
      await claimDefaultLogin(username, password, code);
      await onDone();
    } catch (error) {
      setErrorMsg(extractErrorMessage(error) || "Your username and password couldn't be set. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <>
      <h2 className="login-card-title">Choose your username and password</h2>

      <form onSubmit={handleSubmit} className="login-form">
        <p className="field-hint">
          BitcoinTX still has the login it comes with (admin / password), which anyone could
          guess. Choose your own; your transactions are kept.
        </p>

        <div className="field">
          <label htmlFor="own-username" className="field-label">New Username</label>
          <input
            id="own-username"
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
            autoComplete="username"
            className="input"
          />
        </div>

        <div className="field">
          <label htmlFor="own-password" className="field-label">New Password</label>
          <input
            id="own-password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            autoComplete="new-password"
            aria-describedby="own-password-rule"
            className="input"
          />
          <p id="own-password-rule" className="field-hint">{PASSWORD_RULE}</p>
        </div>

        <div className="field">
          <label htmlFor="own-password-repeat" className="field-label">Repeat New Password</label>
          <input
            id="own-password-repeat"
            type="password"
            value={repeat}
            onChange={(e) => setRepeat(e.target.value)}
            required
            autoComplete="new-password"
            className="input"
          />
        </div>

        <button type="submit" className="btn btn-primary btn-block" disabled={isSubmitting}>
          {isSubmitting ? "Saving…" : "Continue"}
        </button>
        {errorMsg && <div className="note note-error login-error-msg" role="alert">{errorMsg}</div>}
      </form>
    </>
  );
};

export default ChooseOwnLogin;
