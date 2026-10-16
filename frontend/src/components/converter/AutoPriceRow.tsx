import React from "react";
import { Link } from "react-router-dom";

/** Where the live price came from and when, the Dashboard's words in short (#208). */
export interface PriceFrom {
  short: string;
  full: string;
}

/** Auto mode's line: the live price and where it came from, or why there's none and the
 * way forward (#145). At most two lines, so the calculator below stays put. */
const AutoPriceRow: React.FC<{ text: string; why: string | null; from: PriceFrom | null; onTypeAPrice: () => void }> = (
  { text, why, from, onTypeAPrice },
) => (
  <div className="auto-price-row price-mode-row">
    <p className="btc-price">BTC Price: {text}</p>
    {(why === "waiting" || why === "unchosen") && (
      <Link className="converter-action" to="/dashboard">{why === "waiting" ? "Confirm" : "Choose"}</Link>
    )}
    {/* No public site reached through the proxy; never for a site that refused (#241) */}
    {why === "tor" && <span className="converter-note">Is Tor running?</span>}
    {(why === "off" || why === "invalid" || why === "tor" || why === "none") && (
      <button type="button" className="converter-action" onClick={onTypeAPrice}>
        Type a price
      </button>
    )}
    {from && (
      <p className="converter-note price-from" title={from.full}>
        {from.short}
      </p>
    )}
  </div>
);

export default AutoPriceRow;
