import React from "react";
import { NavLink, useNavigate } from "react-router-dom";
import api from "../api";

const Header: React.FC = () => {
  const navigate = useNavigate();

  const handleLogout = async () => {
    const confirmed = window.confirm("Are you sure you want to log out?");
    if (confirmed) {
      await api.post("/logout");
      navigate("/login");
    }
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
