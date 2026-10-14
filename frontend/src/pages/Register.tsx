import React, { useState, useEffect, useRef } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import api from '../api';
import { extractErrorMessage } from '../utils/apiError';
import { useToast } from '../contexts/useToast';
import { CONFIRMATION, extentToConfirm, type LedgerExtent } from '../utils/deleteAll';
import DeleteAllDialog from '../components/DeleteAllDialog';
import { MIN_PASSWORD_LENGTH, PASSWORD_RULE, setupCodeHint, type SetupStatus } from '../utils/credentials';
import '../styles/login.css';

const RegisterPage: React.FC = () => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  // Asked for once the default login has been claimed
  const [overridePassword, setOverridePassword] = useState('');
  // Still the shipped default login; null until the server says
  const [isDefault, setIsDefault] = useState<boolean | null>(null);
  // Claiming the default login needs the first-run setup code.
  const [codeRequired, setCodeRequired] = useState(false);
  const [setupCode, setSetupCode] = useState('');
  // The Mac app, also in a browser at its address
  const [macServer, setMacServer] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  // What a new account would delete: asked once the code or password is right (#256)
  const [toDelete, setToDelete] = useState<LedgerExtent | null>(null);
  const registerButton = useRef<HTMLButtonElement>(null);
  const navigate = useNavigate();
  const toast = useToast();

  useEffect(() => {
    const checkDefaultAccount = async () => {
      try {
        const { data: status } = await api.get<SetupStatus>("/users/setup-status");
        // Still on the shipped admin/password login => first-run setup
        setIsDefault(status.is_default || !status.has_user);
        setCodeRequired(Boolean(status.setup_code_required));
        setMacServer(Boolean(status.desktop));
      } catch {
        // Unknown: treat it as claimed, so the current password is asked for
        setIsDefault(false);
      }
    };
    checkDefaultAccount();
  }, []);

  const handleRegister = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setIsSubmitting(true);
    setErrorMsg("");

    if (username.trim().toLowerCase() === "admin") {
      setErrorMsg("The username 'admin' is reserved and cannot be used. Please choose a different username.");
      setIsSubmitting(false);
      return;
    }

    if (password.length < MIN_PASSWORD_LENGTH) {
      setErrorMsg(`The new password is too short. ${PASSWORD_RULE}`);
      setIsSubmitting(false);
      return;
    }
    if (isDefault && codeRequired && !setupCode.trim()) {
      setErrorMsg(`Enter the setup code. ${setupCodeHint(macServer)}`);
      setIsSubmitting(false);
      return;
    }

    if (isDefault === false && !overridePassword) {
      setErrorMsg("Account is already registered. Enter your current password to proceed.");
      setIsSubmitting(false);
      return;
    }
    await submit();
  };

  /**
   * The server checks the setup code or current password first, then, when
   * the ledger has transactions, answers what would go (409) until the
   * owner confirms in the dialog; then it keeps a copy, deletes them and
   * sets the new login, in one step.
   */
  const submit = async (confirm?: string) => {
    setIsSubmitting(true);
    try {
      await api.post("/users/reset-account", {
        username,
        password,
        current_password: isDefault ? undefined : overridePassword,
        setup_code: isDefault && codeRequired ? setupCode.trim() : undefined,
        confirm,
      });
      toast.success(
        "Registration successful! Your credentials have been updated." +
          (confirm ? " A copy of the database from before is kept in BitcoinTX's data folder (in backups, unencrypted)." : ""),
      );
      navigate('/login');
    } catch (err) {
      const extent = confirm ? null : extentToConfirm(err);
      if (extent) setToDelete(extent);
      else setErrorMsg(extractErrorMessage(err) || "Failed to register. Please try again.");
      if (confirm) setToDelete(null);
    } finally {
      setIsSubmitting(false);
    }
  };

  if (isDefault === null) {
    return <div>Loading...</div>;
  }

  return (
    <div className="login-container">
      <div className="login-header">
        <img src="/icon.svg" alt="BitcoinTX Logo" className="login-logo" />
        <h1 className="login-title">Welcome to BitcoinTX</h1>
      </div>

      <div className="card login-card">
        <h2 className="login-card-title">Register account</h2>

        <form onSubmit={handleRegister} className="login-form">
          <div className="field">
            <label htmlFor="username" className="field-label">New Username</label>
            <input
              id="username"
              type="text"
              value={username}
              onChange={e => setUsername(e.target.value)}
              required
              className="input"
            />
          </div>

          <div className="field">
            <label htmlFor="password" className="field-label">New Password</label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              required
              aria-describedby="password-rule"
              className="input"
            />
            <p id="password-rule" className="field-hint">{PASSWORD_RULE}</p>
          </div>

          {/* A fresh install: the code from the server's log, or the Mac app's data folder */}
          {isDefault && codeRequired && (
            <div className="field">
              <label htmlFor="setup-code" className="field-label">Setup Code</label>
              <input
                id="setup-code"
                type="text"
                value={setupCode}
                onChange={e => setSetupCode(e.target.value)}
                autoComplete="off"
                spellCheck={false}
                placeholder="XXXX-XXXX-XXXX"
                aria-describedby="setup-code-hint"
                className="input"
              />
              <p id="setup-code-hint" className="field-hint">{setupCodeHint(macServer)}</p>
            </div>
          )}

          {isDefault === false && (
            <div className="field">
              <label htmlFor="override" className="field-label">Current Password</label>
              <input
                id="override"
                type="password"
                value={overridePassword}
                onChange={e => setOverridePassword(e.target.value)}
                required
                className="input"
              />
            </div>
          )}

          <button ref={registerButton} type="submit" className="btn btn-primary btn-block" disabled={isSubmitting}>
            {isSubmitting ? "Processing..." : "Register"}
          </button>
          {errorMsg && <div className="note note-error login-error-msg" role="alert">{errorMsg}</div>}
        </form>

        <div className="login-create-account">
          <span className="create-account-text">Already have an account?</span>
          <Link to="/login" className="link">Log in</Link>
        </div>
      </div>
      {toDelete && (
        <DeleteAllDialog
          extent={toDelete}
          title="Create a new account and delete every transaction?"
          canDownloadBackup={false}
          busy={isSubmitting}
          opener={registerButton}
          onConfirm={() => void submit(CONFIRMATION)}
          onCancel={() => setToDelete(null)}
        />
      )}
    </div>
  );
};

export default RegisterPage;
