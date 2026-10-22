import React, { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import api from "../api";

/**
 * /logout: ends the session, then the login page. An address of its own, so
 * leaving a page for it is a navigation the transaction panel can stop with
 * "Discard changes?" before anything is sent (#536).
 */
const LogoutPage: React.FC = () => {
  const navigate = useNavigate();

  useEffect(() => {
    // Only once the server has answered: the login page sends a session
    // still open back to the dashboard (as it does if logging out failed)
    void api
      .post("/logout")
      .catch(() => undefined)
      .then(() => navigate("/login", { replace: true }));
  }, [navigate]);

  return (
    <div className="auth-spinner-container">
      <div className="spinner spinner-lg" role="status" aria-label="Logging out" />
    </div>
  );
};

export default LogoutPage;
