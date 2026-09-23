// FILE: frontend/src/pages/Register.tsx

import React, { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import api from '../api';
import { useToast } from '../contexts/useToast';
import '../styles/login.css';

const RegisterPage: React.FC = () => {
  // States for new credentials.
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  // This state is used only when the default account has been updated already.
  const [overridePassword, setOverridePassword] = useState('');
  // Track whether the current account is still the default account.
  // (Checking if username is "admin" indicates default status.)
  const [isDefault, setIsDefault] = useState<boolean | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const navigate = useNavigate();
  const toast = useToast();

  // On mount, fetch the current user and check if the account is still default.
  useEffect(() => {
    const checkDefaultAccount = async () => {
      try {
        const res = await api.get("/users/setup-status");
        const status = res.data as { has_user: boolean; is_default: boolean };
        // Still on the shipped admin/password login => first-run setup
        setIsDefault(status.is_default || !status.has_user);
      } catch {
        // In case of error, assume registration is not allowed.
        setIsDefault(false);
      }
    };
    checkDefaultAccount();
  }, []);

  const handleRegister = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setIsSubmitting(true);
    setErrorMsg("");

    // ----------------- INSERTED LOGIC -----------------
    // Prevent registration using the reserved username "admin"
    if (username.trim().toLowerCase() === "admin") {
      setErrorMsg("The username 'admin' is reserved and cannot be used. Please choose a different username.");
      setIsSubmitting(false);
      return;
    }
    // ----------------------------------------------------

    // Check registration flow based on account state.
    if (isDefault === false) {
      // If the account is already registered (i.e. not default),
      // require the current password (verified by the server).
      if (!overridePassword) {
        setErrorMsg("Account is already registered. Enter your current password to proceed.");
        setIsSubmitting(false);
        return;
      }
      if (!window.confirm("Warning: The account is already registered. Re-registering will delete all transactions and update your credentials. Proceed?")) {
        setIsSubmitting(false);
        return;
      }
    } else {
      // If the account is still default, confirm the registration action.
      if (!window.confirm("This will update your username and password and delete any existing transactions. Continue?")) {
        setIsSubmitting(false);
        return;
      }
    }

    try {
      // The server verifies authorization (default login, or the current
      // password for an already-registered account), updates the
      // credentials and clears transactions in one step.
      await api.post("/users/reset-account", {
        username,
        password,
        current_password: isDefault ? undefined : overridePassword,
      });

      toast.success("Registration successful! Your credentials have been updated.");
      navigate('/login');
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } }).response?.data?.detail;
      setErrorMsg(detail || "Failed to register. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  };

  // Until the account status is determined, show a loading message.
  if (isDefault === null) {
    return <div>Loading...</div>;
  }

  return (
    <div className="login-container">
      <div className="login-header">
        <img src="/icon.svg" alt="BitcoinTX Logo" className="login-logo" />
        <h1 className="login-title">Welcome to BitcoinTX</h1>
      </div>

      <div className="login-card">
        <h2 className="login-card-title">Register Account</h2>

        <form onSubmit={handleRegister} className="login-form">
          <div className="login-form-group">
            <label htmlFor="username" className="login-label">New Username</label>
            <input
              id="username"
              type="text"
              value={username}
              onChange={e => setUsername(e.target.value)}
              required
              className="login-input"
            />
          </div>

          <div className="login-form-group">
            <label htmlFor="password" className="login-label">New Password</label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              required
              className="login-input"
            />
          </div>

          {/* If the account is already registered, require the current password */}
          {isDefault === false && (
            <div className="login-form-group">
              <label htmlFor="override" className="login-label">Current Password</label>
              <input
                id="override"
                type="password"
                value={overridePassword}
                onChange={e => setOverridePassword(e.target.value)}
                required
                className="login-input"
              />
            </div>
          )}

          <button type="submit" className="accent-btn login-btn" disabled={isSubmitting}>
            {isSubmitting ? "Processing..." : "Register"}
          </button>
          {errorMsg && <div className="login-error-msg">{errorMsg}</div>}
        </form>

        <div className="login-create-account">
          <span className="create-account-text">Already have an account?</span>
          <Link to="/login" className="create-account-link">Log In</Link>
        </div>
      </div>
    </div>
  );
};

export default RegisterPage;
