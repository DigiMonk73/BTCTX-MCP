import React from "react";
import { NavLink, useNavigate } from "react-router-dom";

interface HeaderProps {
  /** Whether the page holds changes not yet saved (the transaction panel). */
  hasUnsavedChanges: () => boolean;
}

const Header: React.FC<HeaderProps> = ({ hasUnsavedChanges }) => {
  const navigate = useNavigate();

  // One question, and nothing sent before its answer: with unsaved changes
  // the transaction panel's "Discard changes?" stops the way to /logout,
  // which logs out (#536); otherwise this one
  const handleLogout = () => {
    if (hasUnsavedChanges() || window.confirm("Are you sure you want to log out?")) navigate("/logout");
  };

  return (
    <header className="header">
      <nav className="header-nav">
        <NavLink
          to="/dashboard"
          className={({ isActive }) =>
            isActive ? "header-nav-item active" : "header-nav-item"
          }
        >
          Dashboard
        </NavLink>
        <NavLink
          to="/transactions"
          className={({ isActive }) =>
            isActive ? "header-nav-item active" : "header-nav-item"
          }
        >
          Transactions
        </NavLink>
        <NavLink
          to="/reports"
          className={({ isActive }) =>
            isActive ? "header-nav-item active" : "header-nav-item"
          }
        >
          Reports
        </NavLink>
        <NavLink
          to="/settings"
          className={({ isActive }) =>
            isActive ? "header-nav-item active" : "header-nav-item"
          }
        >
          Settings
        </NavLink>

        <a
          href="#"
          className="header-nav-item logout-link"
          onClick={(e) => {
            e.preventDefault();
            handleLogout();
          }}
        >
          Logout
        </a>
      </nav>
    </header>
  );
};

export default Header;
