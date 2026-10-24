import React, { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import AboutSetting from "../components/AboutSetting";
import AccountSettings from "../components/AccountSettings";
import BackupRestore from "../components/BackupRestore";
import ConnectAiSetting from "../components/ConnectAiSetting";
import DataManagement from "../components/DataManagement";
import LedgerAccounts from "../components/LedgerAccounts";
import LedgerReview from "../components/LedgerReview";
import type { LedgerReviewResponse } from "../components/ledgerReview/types";
import PriceSourceCard from "../components/priceCard/PriceSourceCard";
import RiverImport from "../components/RiverImport";
import SettingsSection from "../components/SettingsSection";
import { accountsSummary } from "../utils/ledgerAccounts";
import {
  browserStore, initiallyOpen, linkedSection, rememberOpen, reviewSummary, toggled, type SettingsSectionId,
} from "../utils/settingsSections";
import { useSettingsAccounts } from "../utils/useSettingsAccounts";
import "../styles/settings.css";

/**
 * The Settings page: sections that open when asked, one at a time, the open
 * one remembered by this browser, a link such as /settings#privacy opening
 * it (#355, P7's mockups). The Account, Data Management and Backup & Restore
 * sections share one action at a time (their buttons wait while one runs)
 * and the message line below them. About BitcoinTX comes last.
 */
const Settings: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  // The River preview's table takes the window's width while it's open
  const [wide, setWide] = useState(false);
  const { hash, pathname } = useLocation();
  const navigate = useNavigate();
  const [open, setOpen] = useState(() => initiallyOpen(browserStore(), hash));
  const [review, setReview] = useState<LedgerReviewResponse | null>();
  const accounts = useSettingsAccounts();
  const section = { loading, setLoading, setMessage };

  // A link's section opens, as if its button were pressed (remembered), and
  // the link's "#" goes: a reload then shows what's open, not the link's again
  useEffect(() => {
    const linked = linkedSection(hash);
    if (!linked) return;
    setOpen(linked);
    rememberOpen(browserStore(), linked);
    document.getElementById(`settings-${linked}-section`)?.scrollIntoView({ block: "start" });
    navigate(pathname, { replace: true });
  }, [hash, pathname, navigate]);

  const toggle = (id: SettingsSectionId) => {
    const next = toggled(open, id);
    setOpen(next);
    rememberOpen(browserStore(), next);
  };
  const props = (id: SettingsSectionId) => ({ id, open: open === id, onToggle: toggle });

  return (
    <div className={wide && open === "river" ? "settings-page settings-page-wide" : "settings-page"}>
      <h2 className="page-title">Settings</h2>
      <div className="card settings-container">
        <SettingsSection {...props("account")} title="Account"
          summary="Log out, your username and password, the tax timezone, and recalculating the ledger">
          <AccountSettings {...section} />
        </SettingsSection>
        <SettingsSection {...props("accounts")} title="Wallets, exchanges and banks"
          summary={accountsSummary(accounts.book)}>
          <LedgerAccounts {...accounts} />
        </SettingsSection>
        <SettingsSection {...props("review")} title="Ledger Review" region="Ledger review"
          summary={reviewSummary(review)}>
          <LedgerReview onReview={setReview} />
        </SettingsSection>
        <SettingsSection {...props("privacy")} title="Privacy & Network" region="Privacy & network"
          summary="Where BitcoinTX asks for bitcoin prices, and through what">
          <PriceSourceCard variant="settings" />
        </SettingsSection>
        <SettingsSection {...props("ai")} title="Connect an AI Assistant"
          summary="An AI app that reads your ledger and enters transactions, with a key you create">
          <ConnectAiSetting />
        </SettingsSection>
        <SettingsSection {...props("data")} title="Data Management"
          summary="Delete all transactions, or import a CSV file into an empty ledger">
          <DataManagement {...section} />
        </SettingsSection>
        <SettingsSection {...props("river")} title="Import from River"
          summary="River's bitcoin activity file, with a preview before anything is saved">
          <RiverImport onPreviewShown={setWide} book={accounts.book} />
        </SettingsSection>
        <SettingsSection {...props("backup")} title="Backup & Restore"
          summary="A CSV export, an encrypted backup, or a restore from one">
          <BackupRestore {...section} />
        </SettingsSection>
        {message && <p className="note settings-message" role="status">{message}</p>}
        <SettingsSection {...props("about")} title="About BitcoinTX" className="about-section"
          summary="The version, and where to report a problem">
          <AboutSetting />
        </SettingsSection>
      </div>
    </div>
  );
};

export default Settings;
