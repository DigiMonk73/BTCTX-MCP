import React, { useEffect, useRef } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import api from "../api";
import { takeLogoutRequest } from "../utils/logoutRequest";

/**
 * /logout: ends the session, then the login page. An address of its own, so
 * leaving a page for it is a navigation the transaction panel can stop with
 * "Discard changes?" before anything is sent (#536). It logs out only for
 * the Header's Logout (its token, utils/logoutRequest.ts); any other visit
 * goes to the dashboard, or the login page when logged out.
 */
const LogoutPage: React.FC = () => {
  const navigate = useNavigate();
  const token: unknown = (useLocation().state as { logout?: unknown } | null)?.logout;
  // Taken once per visit: React's development mode runs the effect twice
  const asked = useRef<boolean | null>(null);

  useEffect(() => {
    if (asked.current === null) asked.current = takeLogoutRequest(token);
    if (!asked.current) {
      navigate("/dashboard", { replace: true });
      return;
    }
    // Only once the server has answered: the login page sends a session
    // still open back to the dashboard (as it does if logging out failed)
    void api
      .post("/logout")
      .catch(() => undefined)
      .then(() => navigate("/login", { replace: true }));
  }, [navigate, token]);

  return (
    <div className="auth-spinner-container">
      <div className="spinner spinner-lg" role="status" aria-label="Logging out" />
    </div>
  );
};

export default LogoutPage;
