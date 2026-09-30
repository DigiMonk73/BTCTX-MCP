import React, { useEffect, useState } from "react";
import api from "../api";
import { extractErrorMessage } from "../utils/apiError";
import { MIN_PASSWORD_LENGTH, PASSWORD_RULE, SETUP_CODE_HINT } from "../utils/credentials";
import TaxTimezoneSetting from "./TaxTimezoneSetting";

/** The first (and only) user's id, or null. */
async function getUserId(): Promise<number | null> {
  try {
    const res = await api.get("/users/");
    const users = res.data as { id: number; username: string }[];
    return users.length > 0 ? users[0].id : null;
  } catch {
    return null;
  }
}

/** Settings' Account section: log out, change the login, the tax timezone,
 * recalculate the ledger. */
const AccountSettings: React.FC<SettingsSectionProps> = ({ loading, setLoading, setMessage }) => {
  const [newUsername, setNewUsername] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  // Still the default admin/password login (Docker, source): changing it
  // needs the first-run setup code, like Register.
  const [setupCode, setSetupCode] = useState("");
  const [codeRequired, setCodeRequired] = useState(false);

  useEffect(() => {
    api
      .get("/users/setup-status")
      .then((res) => setCodeRequired(Boolean((res.data as { setup_code_required?: boolean }).setup_code_required)))
      .catch(() => setCodeRequired(false));
  }, []);

  const handleLogout = async () => {
    if (!window.confirm("Are you sure you want to log out?")) return;
    setLoading(true);
    setMessage("");
    try {
      await api.post("/logout", {}, { withCredentials: true });
      window.location.href = "/login";
    } catch {
      setMessage("Failed to log out. Please try again.");
    }
    setLoading(false);
  };

  /** Why the new credentials can't be sent yet, or null. */
  const credentialProblem = (): string | null => {
    if (!newUsername && !newPassword) return "Please enter a new username or password (or both).";
    if (newPassword && newPassword.length < MIN_PASSWORD_LENGTH) {
      return `The new password is too short. ${PASSWORD_RULE}`;
    }
    if (!currentPassword) return "Enter your current password to change your username or password.";
    return null;
  };

  const handleCredentialUpdate = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setLoading(true);
    setMessage("");

    if (
      !window.confirm(
        "This will reset your username and password, but keep existing transactions.\n\nContinue?"
      )
    ) {
      setLoading(false);
      return;
    }

    try {
      const userId = await getUserId();
      if (!userId) {
        setMessage("No user found to reset credentials.");
        return;
      }
      const problem = credentialProblem();
      if (problem) {
        setMessage(problem);
        return;
      }

      await api.patch(`/users/${userId}`, {
        username: newUsername || undefined,
        password: newPassword || undefined,
        current_password: currentPassword,
        setup_code: codeRequired ? setupCode.trim() : undefined,
      });

      setMessage("Credentials updated successfully.");
      setNewUsername("");
      setNewPassword("");
      setCurrentPassword("");
      setSetupCode("");
      setCodeRequired(false);
    } catch (error) {
      setMessage(extractErrorMessage(error) || "Failed to reset credentials.");
    } finally {
      setLoading(false);
    }
  };

  const handleRecalculate = async () => {
    setLoading(true);
    setMessage("");
    try {
      const res = await api.post<{ detail: string }>("/transactions/recalculate");
      setMessage(res.data.detail);
    } catch {
      setMessage("Recalculation failed. Your data was not changed.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="settings-section" role="region" aria-label="Account">
      <h3 className="section-title">Account</h3>

      <div className="settings-option">
        <div className="option-info">
          <span className="settings-option-title">Logout</span>
          <p className="settings-option-subtitle">Sign out of your account.</p>
        </div>
        <button onClick={handleLogout} disabled={loading} className="btn btn-secondary">
          {loading ? "Processing..." : "Logout"}
        </button>
      </div>

      <div className="settings-option stacked">
        <div className="option-info">
          <span className="settings-option-title">Reset Username &amp; Password</span>
          <p className="settings-option-subtitle">
            Change your username and password without deleting any transactions.
          </p>
        </div>

        <form onSubmit={handleCredentialUpdate} className="credential-update-form">
          <div className="credential-inputs">
            <input
              type="text"
              placeholder="New Username"
              aria-label="New username"
              value={newUsername}
              onChange={(e) => setNewUsername(e.target.value)}
              className="input"
            />
            <input
              type="password"
              placeholder="New Password"
              aria-label="New password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              autoComplete="new-password"
              className="input"
            />
            <input
              type="password"
              placeholder="Current Password"
              aria-label="Current password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              autoComplete="current-password"
              className="input"
            />
            {codeRequired && (
              <input
                type="text"
                placeholder="Setup Code"
                aria-label="Setup code"
                value={setupCode}
                onChange={(e) => setSetupCode(e.target.value)}
                autoComplete="off"
                spellCheck={false}
                className="input"
              />
            )}
            <p className="field-hint">
              New password: {PASSWORD_RULE.toLowerCase()} Any change needs your current password.
              {codeRequired && ` This is still the default login: changing it needs the setup code. ${SETUP_CODE_HINT}`}
            </p>
          </div>

          <div className="credential-submit-container">
            <button type="submit" className="btn btn-primary" disabled={loading}>
              {loading ? "Processing..." : "Update"}
            </button>
          </div>
        </form>
      </div>

      <TaxTimezoneSetting />

      <div className="settings-option">
        <div className="option-info">
          <span className="settings-option-title">Recalculate Ledger</span>
          <p className="settings-option-subtitle">
            Rebuild all lots, balances and gains from your transactions. Run once after
            upgrading BitcoinTX so calculation fixes apply to existing data.
          </p>
        </div>
        <button onClick={handleRecalculate} disabled={loading} className="btn btn-secondary">
          {loading ? "Processing..." : "Recalculate"}
        </button>
      </div>
    </div>
  );
};

export default AccountSettings;
