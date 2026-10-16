import React, { useEffect, useReducer, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import api from '../api';
import { extractErrorMessage } from '../utils/apiError';
import "../styles/login.css";
import { ensureTaxTimezone } from "../utils/taxTimezone";
import { setupCodeHint, type SetupStatus } from "../utils/credentials";
import { appWindowApi, onAppWindowApi } from "../utils/appWindow";
import ChooseOwnLogin from "../components/ChooseOwnLogin";
import { NO_SETUP_CODE, windowSetupCode } from "../utils/ownLogin";

const LoginPage: React.FC = () => {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false); // For toggling password visibility
  const navigate = useNavigate();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");
  // Still on the default login: logging in needs the setup code (an older
  // install with data logs in this way, then changes the password).
  const [codeRequired, setCodeRequired] = useState(false);
  // Only while the account is still the shipped default login: then
  // /register claims it. Afterwards that page resets the account
  // (deleting every transaction), which "Create account" would hide.
  const [firstRun, setFirstRun] = useState(false);
  // The Mac app, also in a browser at its address, without its window
  const [macServer, setMacServer] = useState(false);
  const [setupCode, setSetupCode] = useState("");
  // The Mac app's own window, which can supply the setup code itself:
  // there the owner chooses a login instead (ChooseOwnLogin). Read at every
  // render: pywebview fills it in after the page loads, then says so.
  const [, windowChanged] = useReducer((n: number) => n + 1, 0);
  useEffect(() => onAppWindowApi(windowChanged), []);
  const windowApi = appWindowApi();
  // Whether the window could read the code: if not, the sign-in form with
  // its Setup Code field, so the owner is never stuck
  const [windowHasCode, setWindowHasCode] = useState<boolean | null>(null);
  const readsCode = Boolean(firstRun && windowApi?.setup_code);
  useEffect(() => {
    if (!readsCode) return;
    void windowSetupCode(appWindowApi()).then((code) => {
      setWindowHasCode(Boolean(code));
      if (!code) setErrorMsg(NO_SETUP_CODE);
    });
  }, [readsCode]);
  const noCode = () => {
    setWindowHasCode(false);
    setErrorMsg(NO_SETUP_CODE);
  };
  useEffect(() => {
    api
      .get('/protected')
      .then(() => {
        navigate('/dashboard');
      })
      .catch(() => {
        // Not logged in — stay on login page
      });
    api
      .get<SetupStatus>("/users/setup-status")
      .then((res) => {
        setCodeRequired(Boolean(res.data.setup_code_required));
        setFirstRun(Boolean(res.data.is_default));
        setMacServer(Boolean(res.data.desktop));
      })
      .catch(() => undefined);
  }, [navigate]);

  const enterApp = async () => {
    // While the ledger is empty, adopt this computer's timezone for tax dates (changeable in Settings)
    await ensureTaxTimezone();
    navigate("/dashboard");
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    setErrorMsg("");

    try {
      await api.post("/login", {
        username,
        password,
        setup_code: codeRequired && setupCode.trim() ? setupCode.trim() : undefined,
      });
      await enterApp();
    } catch (error) {
      const message = extractErrorMessage(error);
      setErrorMsg(message || "Login failed. Please check your username/password.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const toggleShowPassword = () => {
    setShowPassword((prev) => !prev);
  };

  return (
    <div className="login-container">
      <div className="login-header">
        <img src="/icon.svg" alt="BitcoinTX Logo" className="login-logo" />
        <h1 className="login-title">Welcome to BitcoinTX</h1>
      </div>

      <div className="card login-card">
        {readsCode && windowApi && windowHasCode !== false ? (
          <ChooseOwnLogin windowApi={windowApi} onDone={enterApp} onNoCode={noCode} />
        ) : (
          <>
            <h2 className="login-card-title">Sign in</h2>

            <form onSubmit={handleSubmit} className="login-form">
              <div className="field">
                <label htmlFor="username" className="field-label">
                  Username
                </label>
                <input
                  id="username"
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  required
                  className="input"
                />
              </div>

              <div className="field">
                <div className="password-label-row">
                  <label htmlFor="password" className="field-label">
                    Password
                  </label>
                  <button
                    type="button"
                    className="link toggle-password-btn"
                    onClick={toggleShowPassword}
                  >
                    {showPassword ? "Hide password" : "Show password"}
                  </button>
                </div>

                <input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  className="input"
                />
              </div>

              {codeRequired && (
                <div className="field">
                  <label htmlFor="login-setup-code" className="field-label">
                    Setup Code
                  </label>
                  <input
                    id="login-setup-code"
                    type="text"
                    value={setupCode}
                    onChange={(e) => setSetupCode(e.target.value)}
                    autoComplete="off"
                    spellCheck={false}
                    placeholder="XXXX-XXXX-XXXX"
                    aria-describedby="login-setup-code-hint"
                    className="input"
                  />
                  <p id="login-setup-code-hint" className="field-hint">
                    Only while this install still has the default login (admin / password).{" "}
                    {setupCodeHint(Boolean(windowApi) || macServer)}
                    {(windowApi || macServer) && " Once logged in, set your own username and password in Settings."}
                  </p>
                </div>
              )}

              <button
                type="submit"
                className="btn btn-primary btn-block"
                disabled={isSubmitting}
              >
                {isSubmitting ? "Logging in…" : "Log in"}
              </button>
              {errorMsg && <div className="note note-error login-error-msg" role="alert">{errorMsg}</div>}
            </form>

            {firstRun && (
              <div className="login-create-account">
                <span className="create-account-text">Don’t have an account?</span>
                <Link to="/register" className="link">
                  Create account
                </Link>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
};

export default LoginPage;
