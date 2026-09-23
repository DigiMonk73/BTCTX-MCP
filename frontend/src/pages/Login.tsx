import React, { useState, useEffect } from "react";
import { useNavigate, Link } from "react-router-dom";
import api from '../api';
import { extractErrorMessage } from '../hooks/useApiCall';
import "../styles/login.css";
import { ensureTaxTimezone } from "../utils/taxTimezone";

const LoginPage: React.FC = () => {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false); // For toggling password visibility
  const navigate = useNavigate();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");
  useEffect(() => {
    api
      .get('/protected')
      .then(() => {
        navigate('/dashboard');
      })
      .catch(() => {
        // Not logged in — stay on login page
      });
  }, [navigate]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    setErrorMsg("");

    try {
      await api.post("/login", { username, password });
      // First login: adopt this computer's timezone for tax dates (changeable in Settings)
      await ensureTaxTimezone();
      navigate("/dashboard");
    } catch (error) {
      const message = extractErrorMessage(error);
      setErrorMsg(message || "Login failed. Please check your username/password.");
    } finally {
      setIsSubmitting(false);
    }
  };

  /** Toggle input type between 'password' and 'text' */
  const toggleShowPassword = () => {
    setShowPassword((prev) => !prev);
  };

  return (
    <div className="login-container">
      <div className="login-header">
        <img src="/icon.svg" alt="BitcoinTX Logo" className="login-logo" />
        <h1 className="login-title">Welcome to BitcoinTX</h1>
      </div>

      <div className="login-card">
        <h2 className="login-card-title">Sign In</h2>

        <form onSubmit={handleSubmit} className="login-form">
          {/* ---------- USERNAME FIELD ---------- */}
          <div className="login-form-group">
            <label htmlFor="username" className="login-label">
              Username
            </label>
            <input
              id="username"
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              className="login-input"
            />
          </div>

          {/* ---------- PASSWORD FIELD WITH 'SHOW PASSWORD' TEXT ABOVE THE LABEL ---------- */}
          <div className="login-form-group">
            {/* Row for label + show/hide link */}
            <div className="password-label-row">
              <label htmlFor="password" className="login-label">
                Password
              </label>
              <button
                type="button"
                className="toggle-password-btn"
                onClick={toggleShowPassword}
              >
                {showPassword ? "Hide Password" : "Show Password"}
              </button>
            </div>

            {/* Actual password input below */}
            <input
              id="password"
              type={showPassword ? "text" : "password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="login-input"
            />
          </div>

          <button
            type="submit"
            className="accent-btn login-btn"
            disabled={isSubmitting}
          >
            {isSubmitting ? "Logging in..." : "Log In"}
          </button>
          {errorMsg && <div className="login-error-msg">{errorMsg}</div>}
        </form>

        <div className="login-create-account">
          <span className="create-account-text">Don’t have an account?</span>
          <Link to="/register" className="create-account-link">
            Create Account
          </Link>
        </div>
      </div>
    </div>
  );
};

export default LoginPage;
