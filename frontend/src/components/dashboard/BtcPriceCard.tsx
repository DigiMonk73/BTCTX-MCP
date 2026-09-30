import React from "react";
import { Blocks } from "lucide-react";
import type { LivePrice } from "../../utils/dashboard";
import { formatUsd } from "../../utils/format";

interface BtcPriceCardProps {
  price: LivePrice;
  blockHeight: number | null;
}

/** Today's BTC price, or why there is none, and the block height. */
const BtcPriceCard: React.FC<BtcPriceCardProps> = ({ price, blockHeight }) => (
  <div className="card btc-price-container">
    <div className="btc-price-header">
      <h3 className="card-title">Current Bitcoin Price</h3>
    </div>

    <div className="btc-price-large">
      <svg
        className="btc-watermark"
        viewBox="0 0 64 64"
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden="true"
      >
        <circle cx="32" cy="32" r="32" fill="currentColor" />
        <path
          className="btc-watermark-mark"
          d="M46.1 27.4c.6-4.1-2.5-6.3-6.8-7.8l1.4-5.6-3.4-.8-1.4 5.4c-.9-.2-1.8-.4-2.7-.7l1.4-5.5-3.4-.8-1.4 5.6c-.7-.2-1.5-.4-2.2-.5l-4.7-1.2-.9 3.6s2.5.6 2.5.6c1.4.3 1.6 1.2 1.6 1.9l-1.6 6.4c.1 0 .2 0 .3.1-.1 0-.2-.1-.3-.1l-2.2 9c-.2.4-.6 1.1-1.6.8 0 0-2.5-.6-2.5-.6l-1.7 3.9 4.4 1.1c.8.2 1.6.4 2.4.6l-1.4 5.7 3.4.8 1.4-5.6c.9.3 1.8.5 2.7.7l-1.4 5.5 3.4.8 1.4-5.6c5.9 1.1 10.3.7 12.2-4.7 1.5-4.3-.1-6.8-3.2-8.4 2.3-.5 4-2.1 4.4-5.2zm-7.9 11.1c-1.1 4.3-8.3 2-10.7 1.4l1.9-7.6c2.4.6 9.9 1.8 8.8 6.2zm1.1-11.2c-1 3.9-7 1.9-9 1.4l1.7-6.9c2 .5 8.4 1.4 7.3 5.5z"
        />
      </svg>
      {price.loading ? (
        <span className="btc-price-value">Loading...</span>
      ) : price.value !== null ? (
        <span className="btc-price-value">
          {formatUsd(price.value)}
        </span>
      ) : price.off ? (
        <span className="btc-price-value" title={price.problem || "Settings → Privacy & network"}>Prices off</span>
      ) : (
        <span className="btc-price-value" title={price.problem}>Error</span>
      )}
    </div>

    {blockHeight !== null && (
      <div className="btc-block-height">
        <Blocks size={14} aria-hidden="true" />
        <span>Block Height: {blockHeight.toLocaleString()}</span>
      </div>
    )}
  </div>
);

export default BtcPriceCard;
