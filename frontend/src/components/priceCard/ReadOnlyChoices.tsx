import React from "react";
import { Lock } from "lucide-react";
import {
  PRICE_CHOICES,
  isOnion,
  managedBanner,
  shownAddress,
  type NetworkSettingsData,
} from "../../utils/priceSource";

/**
 * The choice the server sets (StartOS's action, or a Docker server's
 * BTCTX_ settings), read-only. "Chosen" is said in words: a disabled
 * control carries no information, and some can't be focused or read.
 */
const ReadOnlyChoices: React.FC<{ settings: NetworkSettingsData }> = ({ settings }) => {
  const banner = managedBanner(settings);
  const mempool = shownAddress(settings, "mempool");
  const tor = shownAddress(settings, "tor");
  return (
    <>
      {banner && (
        <p className="note price-banner">
          <Lock size={14} aria-hidden="true" /> {banner}
        </p>
      )}
      {settings.invalid ? null /* the status line says so */ : (
        <ul className="price-choices read-only" aria-label="Where BitcoinTX gets newer prices">
          {PRICE_CHOICES.map((c) => {
            const chosen = c.value === settings.price_source;
            return (
              <li key={c.value} className={chosen ? "price-choice chosen" : "price-choice"}>
                <span className="price-choice-label">
                  {c.label}
                  {chosen && <span className="badge badge-accent">✓ Chosen</span>}
                </span>
                <span className="price-help">{c.help}</span>
                {chosen && c.value === "mempool" && (
                  <span className="price-detail">
                    {mempool ?? "No address"}
                    {settings.mempool_fallback ? " · if it can't answer, public price sites" : ""}
                  </span>
                )}
                {chosen && tor && (c.value === "public" || settings.mempool_fallback || isOnion(settings.mempool_url ?? "")) && (
                  <span className="price-detail">Through Tor: {tor}</span>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </>
  );
};

export default ReadOnlyChoices;
