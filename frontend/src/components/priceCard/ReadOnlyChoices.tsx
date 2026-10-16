import React from "react";
import { Lock } from "lucide-react";
import {
  PRICE_CHOICES,
  isOnion,
  managedBanner,
  shownAddress,
  type NetworkSettingsData,
  type PriceChoice,
} from "../../utils/priceSource";

/** Under the chosen one: your Mempool's address and backup, and Tor's. */
const ChosenDetails: React.FC<{ choice: PriceChoice; settings: NetworkSettingsData }> = ({ choice: c, settings }) => {
  const mempool = shownAddress(settings, "mempool");
  const tor = shownAddress(settings, "tor");
  return (
    <>
      {c.value === "mempool" && (
        <span className="price-detail">
          {mempool ?? "No address"}
          {settings.mempool_fallback ? " · if it can't answer, public price sites" : ""}
        </span>
      )}
      {tor && (c.value === "public" || settings.mempool_fallback || isOnion(settings.mempool_url ?? "")) && (
        <span className="price-detail">Through Tor: {tor}</span>
      )}
    </>
  );
};

/** One choice of the read-only list. */
const ReadOnlyChoice: React.FC<{ choice: PriceChoice; settings: NetworkSettingsData }> = ({ choice: c, settings }) => {
  const chosen = c.value === settings.price_source;
  // Your Mempool set by StartOS (#145 plan 2.4, #208): the most private choice, as its action says
  const recommended = chosen && c.value === "mempool" && settings.host === "startos";
  return (
    <li className={chosen ? "price-choice chosen" : "price-choice"}>
      <span className="price-choice-label">
        {c.label}
        {chosen && <span className="badge badge-accent">✓ Chosen</span>}
        {recommended && <span className="badge">Recommended</span>}
      </span>
      <span className="price-help">{c.help}</span>
      {chosen && <ChosenDetails choice={c} settings={settings} />}
    </li>
  );
};

/**
 * The choice the server sets (StartOS's action, or a Docker server's
 * BTCTX_ settings), read-only. "Chosen" is said in words: a disabled
 * control carries no information, and some can't be focused or read.
 */
const ReadOnlyChoices: React.FC<{ settings: NetworkSettingsData }> = ({ settings }) => {
  const banner = managedBanner(settings);
  return (
    <>
      {banner && (
        <p className="note price-banner">
          <Lock size={14} aria-hidden="true" /> {banner}
        </p>
      )}
      {settings.invalid ? null /* the status line says so */ : (
        <ul className="price-choices read-only" aria-label="Where BitcoinTX gets newer prices">
          {PRICE_CHOICES.map((c) => <ReadOnlyChoice key={c.value} choice={c} settings={settings} />)}
        </ul>
      )}
    </>
  );
};

export default ReadOnlyChoices;
