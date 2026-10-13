import React, { useState } from "react";
import AboutSetting from "../components/AboutSetting";
import AccountSettings from "../components/AccountSettings";
import BackupRestore from "../components/BackupRestore";
import ConnectAiSetting from "../components/ConnectAiSetting";
import DataManagement from "../components/DataManagement";
import LedgerReview from "../components/LedgerReview";
import PriceSourceCard from "../components/priceCard/PriceSourceCard";
import RiverImport from "../components/RiverImport";
import "../styles/settings.css";

/**
 * The Settings page. The Account, Data Management and Backup & Restore
 * sections share one action at a time (their buttons wait while one runs)
 * and the message line below them. About BitcoinTX comes last.
 */
const Settings: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const section = { loading, setLoading, setMessage };

  return (
    <div className="settings-page">
      <h2 className="page-title">Settings</h2>
      <div className="card settings-container">
        <AccountSettings {...section} />
        <LedgerReview />
        <div className="settings-section" role="region" aria-label="Privacy & network">
          <h3 className="section-title">Privacy &amp; Network</h3>
          <PriceSourceCard variant="settings" />
        </div>
        <ConnectAiSetting />
        <DataManagement {...section} />
        <RiverImport />
        <BackupRestore {...section} />
        {message && <p className="note settings-message" role="status">{message}</p>}
        <AboutSetting />
      </div>
    </div>
  );
};

export default Settings;
