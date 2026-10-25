import React, { useEffect, useRef, useState } from "react";
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
  // Ledger Review asked again once another section saved what it reads (#645)
  const [reviewRound, setReviewRound] = useState(0);
  const reviewAgain = () => setReviewRound((n) => n + 1);
  const accounts = useSettingsAccounts();
  const section = { loading, setLoading, setMessage };

  // A link's section opens, as if its button were pressed (remembered), and
  // the link's "#" goes: a reload then shows what's open, not the link's again
  const [scrollTo, setScrollTo] = useState<SettingsSectionId | null>(null);
  useEffect(() => {
    const linked = linkedSection(hash);
    if (!linked) return;
    setOpen(linked);
    rememberOpen(browserStore(), linked);
    setScrollTo(linked);
    navigate(pathname, { replace: true });
  }, [hash, pathname, navigate]);
  // Once it's open and the one before has closed, so the place it scrolls to holds
  useEffect(() => {
    if (!scrollTo || open !== scrollTo) return;
    document.getElementById(`settings-${scrollTo}-section`)?.scrollIntoView({ block: "start" });
    setScrollTo(null);
  }, [scrollTo, open]);

  // Closed sections stay mounted, and two of them save transactions (the imports, Delete All): the accounts
  // section reads the book again each time it opens, by its button or a link, as its rows offer Delete and Add
  // its note by `in_use` (#720). Open as the page opens, it has the book useSettingsAccounts just read.
  const accountsOpen = open === "accounts";
  const accountsWereOpen = useRef(accountsOpen);
  const { reload: readAccounts } = accounts;
  useEffect(() => {
    if (accountsOpen && !accountsWereOpen.current) void readAccounts();
    accountsWereOpen.current = accountsOpen;
  }, [accountsOpen, readAccounts]);

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
          <AccountSettings {...section} onFiguresChanged={reviewAgain} />
        </SettingsSection>
        <SettingsSection {...props("accounts")} title="Wallets, exchanges and banks"
          summary={accountsSummary(accounts.book)}>
          <LedgerAccounts {...accounts} onFiguresChanged={reviewAgain} />
        </SettingsSection>
        <SettingsSection {...props("review")} title="Ledger Review" region="Ledger review"
          summary={reviewSummary(review)}>
          <LedgerReview onReview={setReview} round={reviewRound} />
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
        <SettingsSection {...props("river")} title="Import from an exchange"
          summary="River's, Coinbase's, Kraken's, Strike's, Swan's, Cash App's or another exchange's file, with a preview before anything is saved">
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
