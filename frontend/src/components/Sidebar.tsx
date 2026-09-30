import React from 'react';
import logo from '../assets/logo.svg';
import Calculator from './Calculator';
import BtcConverter from './BtcConverter';
import "../styles/app.css";

/** The logo and name at the top of the sidebar. */
const SidebarBrand: React.FC = () => {
  return (
    <div className="sidebar-brand">
      <img src={logo} alt="BitcoinTX Logo" className="sidebar-logo" />
      <div className="sidebar-title">BitcoinTX</div>
    </div>
  );
};

/** The sidebar's tools: the sats converter above the calculator. */
const SidebarTools: React.FC = () => {
  return (
    <div className="sidebar-tools">
      <div className="sidebar-converter">
        <BtcConverter />
      </div>

      <div className="sidebar-calculator">
        <Calculator />
      </div>
    </div>
  );
};

/** The sidebar: the brand, then the tools. The page links are in the header. */
const Sidebar: React.FC = () => {
  return (
    <aside className="sidebar">
      <SidebarBrand />

      <SidebarTools />
    </aside>
  );
};

export default Sidebar;
