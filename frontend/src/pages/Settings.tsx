import React, { useState } from "react";
import AccountSettings from "../components/AccountSettings";
import BackupRestore from "../components/BackupRestore";
import ConnectAiSetting from "../components/ConnectAiSetting";
import DataManagement from "../components/DataManagement";
import LedgerReview from "../components/LedgerReview";
import NetworkSettings from "../components/NetworkSettings";
import RiverImport from "../components/RiverImport";
import "../styles/settings.css";

/**
 * The Settings page. The Account, Data Management and Backup & Restore
 * sections share one action at a time (their buttons wait while one runs)
 * and the message line at the bottom.
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
        <NetworkSettings />
        <ConnectAiSetting />
        <DataManagement {...section} />
        <RiverImport />
        <BackupRestore {...section} />
        {message && <p className="note settings-message" role="status">{message}</p>}
      </div>
    </div>
  );
};

export default Settings;
