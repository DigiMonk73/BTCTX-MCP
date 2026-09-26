import axios from "axios";
import React, { useEffect, useState } from "react";
import { Blocks } from "lucide-react";
import api from "../api"; // Centralized API client
import "../styles/dashboard.css";

// Numeric helpers
import {
  parseDecimal,
  formatUsd, formatSignedUsd,
  formatBtc,
  parseGainsAndLosses,
} from "../utils/format";

const Dashboard: React.FC = () => {
  // ------------------ 1) STATE DECLARATIONS ------------------
  const [balances, setBalances] = useState<AccountBalance[] | null>(null);
  const [bankBalance, setBankBalance] = useState<number>(0);
  const [exchangeUSDBalance, setExchangeUSDBalance] = useState<number>(0);
  const [exchangeBTCBalance, setExchangeBTCBalance] = useState<number>(0);
  const [walletBTCBalance, setWalletBTCBalance] = useState<number>(0);
  const [totalBTC, setTotalBTC] = useState<number>(0);
  // Removed totalUSD since it’s unused

  // Cost basis & Gains
  const [averageBtcCostBasis, setAverageBtcCostBasis] = useState<number | null>(null);
  const [gainsAndLosses, setGainsAndLosses] = useState<GainsAndLosses | null>(null);

  // BTC Price, Block Height & error states
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [currentBtcPrice, setCurrentBtcPrice] = useState<number | null>(null);
  const [isPriceLoading, setIsPriceLoading] = useState(true);
  const [blockHeight, setBlockHeight] = useState<number | null>(null);
  // Settings → Privacy & network: live data turned off (the server answers 503)
  const [liveDataOff, setLiveDataOff] = useState(false);

  // ------------------ 2) FETCH LIVE BTC PRICE ------------------
  useEffect(() => {
    setIsPriceLoading(true);
    api
      .get("/bitcoin/price")
      .then((res) => {
        if (res.data && res.data.USD) {
          setCurrentBtcPrice(res.data.USD);
        }
      })
      .catch((err) => {
        // Price fetch failed - shown as "Error", or "Live data off" by choice
        if (axios.isAxiosError(err) && err.response?.status === 503) setLiveDataOff(true);
      })
      .finally(() => {
        setIsPriceLoading(false);
      });
  }, []);

  // ------------------ 2b) FETCH BLOCK HEIGHT ------------------
  useEffect(() => {
    api
      .get("/bitcoin/blockheight")
      .then((res) => {
        if (res.data && res.data.height) {
          setBlockHeight(res.data.height);
        }
      })
      .catch(() => {
        // Block height fetch failed silently - will show as null
      });
  }, []);

  // ------------------ 3) FETCH AVERAGE COST BASIS ------------------
  useEffect(() => {
    api
      .get<AverageCostBasis>("/calculations/average-cost-basis")
      .then((res) => {
        setAverageBtcCostBasis(res.data.averageCostBasis);
      })
      .catch(() => {
        // Cost basis fetch failed silently
      });
  }, []);

  // ------------------ 4) FETCH ACCOUNT BALANCES ------------------
  useEffect(() => {
    api
      .get("/calculations/accounts/balances")
      .then((response) => {
        const data = response.data;
        if (!Array.isArray(data)) {
          throw new Error("Data is not an array. Received: " + JSON.stringify(data));
        }
        setBalances(data as AccountBalance[]);
      })
      .catch((err) => {
        setFetchError(err instanceof Error ? err.message : "Failed to load balances");
      });
  }, []);

  // ------------------ 5) CALCULATE TOTALS ------------------
  useEffect(() => {
    if (!balances) return;

    let bank = 0;
    let exchUSD = 0;
    let exchBTC = 0;
    let wBTC = 0;
    let totalBtcTemp = 0;

    balances.forEach((acc) => {
      const numericBalance = parseDecimal(acc.balance);
      if (Number.isNaN(numericBalance)) {
        return; // Skip invalid balances
      }
      // Skip fee accounts
      if (acc.name === "BTC Fees" || acc.name === "USD Fees") {
        return;
      }
      // Identify known accounts
      if (acc.name === "Bank" && acc.currency === "USD") {
        bank = numericBalance;
      } else if (acc.name === "Wallet" && acc.currency === "BTC") {
        wBTC = numericBalance;
      } else if (acc.name === "Exchange USD" && acc.currency === "USD") {
        exchUSD = numericBalance;
      } else if (acc.name === "Exchange BTC" && acc.currency === "BTC") {
        exchBTC = numericBalance;
      }

      // Tally BTC total
      if (acc.currency === "BTC") {
        totalBtcTemp += numericBalance;
      }
    });

    setBankBalance(bank);
    setExchangeUSDBalance(exchUSD);
    setExchangeBTCBalance(exchBTC);
    setWalletBTCBalance(wBTC);
    setTotalBTC(totalBtcTemp);
  }, [balances]);

  // ------------------ 6) FETCH GAINS & LOSSES ------------------
  useEffect(() => {
    api
      .get<GainsAndLossesRaw>("/calculations/gains-and-losses")
      .then((response) => {
        const parsed = parseGainsAndLosses(response.data);
        setGainsAndLosses(parsed);
      })
      .catch((err) => {
        setFetchError(err instanceof Error ? err.message : "Failed to load gains/losses");
      });
  }, []);

  // ------------------ 7) ERROR / LOADING HANDLING ------------------
  if (fetchError) {
    return (
      <div className="dashboard">
        <div className="card dashboard-error" role="alert">
          <h2 className="card-title">Couldn't load your dashboard</h2>
          <p className="note note-error">{fetchError}</p>
        </div>
      </div>
    );
  }

  if (balances === null || gainsAndLosses === null) {
    return (
      <div className="dashboard" aria-busy="true">
        <div className="dashboard-grid">
          {["Portfolio Overview", "Current Bitcoin Price", "Realized Gains/Losses (FIFO)", "Income & Fees"].map(
            (title) => (
              <div key={title} className="card dashboard-card-loading">
                <h3 className="card-title">{title}</h3>
                <div className="loading-row">
                  <div className="spinner" /> Loading…
                </div>
              </div>
            ),
          )}
        </div>
      </div>
    );
  }

  // ------------------ 8) UNREALIZED GAINS HELPER ------------------
  const renderUnrealizedGains = () => {
    if (isPriceLoading || currentBtcPrice === null || averageBtcCostBasis === null) {
      return "Loading...";
    }
    const gains = (currentBtcPrice - averageBtcCostBasis) * totalBTC;
    const isGain = gains >= 0;
    return (
      <span className={isGain ? "text-gain" : "text-loss"}>
        {formatSignedUsd(gains)}
      </span>
    );
  };

  // ------------------ 9) RENDER DASHBOARD ------------------
  return (
    <div className="dashboard">
      {/* =================== TOP ROW: 2 CARDS =================== */}
      <div className="dashboard-grid">
        {/* (1) Portfolio Overview */}
        <div className="card portfolio-overview">
          <h3 className="card-title">Portfolio Overview</h3>

          {/* Label on left, value on right (like Gains & Losses) */}
          <p>
            <strong>Bank (USD)</strong>
            <span>{formatUsd(bankBalance)}</span>
          </p>
          <p>
            <strong>Exchange (USD)</strong>
            <span>{formatUsd(exchangeUSDBalance)}</span>
          </p>
          <p>
            <strong>Exchange (BTC)</strong>
            <span>{formatBtc(exchangeBTCBalance)}</span>
          </p>
          <p>
            <strong>Wallet (BTC)</strong>
            <span>{formatBtc(walletBTCBalance)}</span>
          </p>

          <hr />

          <p>
            <strong>Total BTC</strong>
            <span>{formatBtc(totalBTC)}</span>
          </p>
          <p>
            <strong>BTC Cost Basis</strong>
            <span>
              {averageBtcCostBasis !== null ? formatUsd(averageBtcCostBasis) : "Loading..."}
            </span>
          </p>
          <p>
            <strong>Unrealized Gains/Losses</strong>
            <span>{renderUnrealizedGains()}</span>
          </p>
        </div>

        {/* (2) Current Bitcoin Price */}
        <div className="card btc-price-container">
          {/* Title row with logo on the left, heading on the right */}
          <div className="btc-price-header">
            <h3 className="card-title">Current Bitcoin Price</h3>
          </div>

          {/* The big orange price in the center */}
          <div className="btc-price-large">
            {/* Bitcoin watermark icon */}
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
            {isPriceLoading ? (
              <span className="btc-price-value">Loading...</span>
            ) : currentBtcPrice !== null ? (
              <span className="btc-price-value">
                {formatUsd(currentBtcPrice)}
              </span>
            ) : liveDataOff ? (
              <span className="btc-price-value" title="Settings → Privacy & network">Live data off</span>
            ) : (
              <span className="btc-price-value">Error</span>
            )}
          </div>

          {/* Block height footer */}
          {blockHeight !== null && (
            <div className="btc-block-height">
              <Blocks size={14} aria-hidden="true" />
              <span>Block Height: {blockHeight.toLocaleString()}</span>
            </div>
          )}
        </div>

        {/* (3) Realized Gains/Losses (FIFO) */}
        <div className="card realized-gains-container">
          <h3 className="card-title">Realized Gains/Losses (FIFO)</h3>

          <p>
            <strong>Short-Term Gains</strong>
            <span className={gainsAndLosses.short_term_gains > 0 ? "text-gain" : ""}>
              {formatSignedUsd(gainsAndLosses.short_term_gains)}
            </span>
          </p>
          <p>
            <strong>Short-Term Losses</strong>
            <span className={gainsAndLosses.short_term_losses > 0 ? "text-loss" : ""}>
              {formatUsd(-gainsAndLosses.short_term_losses)}
            </span>
          </p>
          <p>
            <strong>Net Short-Term</strong>
            <span
              className={
                gainsAndLosses.short_term_net > 0
                  ? "text-gain"
                  : gainsAndLosses.short_term_net < 0
                  ? "text-loss"
                  : ""
              }
            >
              {formatSignedUsd(gainsAndLosses.short_term_net)}
            </span>
          </p>

          <hr />

          <p>
            <strong>Long-Term Gains</strong>
            <span className={gainsAndLosses.long_term_gains > 0 ? "text-gain" : ""}>
              {formatSignedUsd(gainsAndLosses.long_term_gains)}
            </span>
          </p>
          <p>
            <strong>Long-Term Losses</strong>
            <span className={gainsAndLosses.long_term_losses > 0 ? "text-loss" : ""}>
              {formatUsd(-gainsAndLosses.long_term_losses)}
            </span>
          </p>
          <p>
            <strong>Net Long-Term</strong>
            <span
              className={
                gainsAndLosses.long_term_net > 0
                  ? "text-gain"
                  : gainsAndLosses.long_term_net < 0
                  ? "text-loss"
                  : ""
              }
            >
              {formatSignedUsd(gainsAndLosses.long_term_net)}
            </span>
          </p>

          <hr />

          <p>
            <strong>Total Net Capital Gains</strong>
            <span
              className={
                gainsAndLosses.total_net_capital_gains > 0
                  ? "text-gain"
                  : gainsAndLosses.total_net_capital_gains < 0
                  ? "text-loss"
                  : ""
              }
            >
              {formatSignedUsd(gainsAndLosses.total_net_capital_gains)}
            </span>
          </p>
          <p>
            <strong>Year to Date Gains</strong>
            <span
              className={
                gainsAndLosses.year_to_date_capital_gains > 0
                  ? "text-gain"
                  : gainsAndLosses.year_to_date_capital_gains < 0
                  ? "text-loss"
                  : ""
              }
            >
              {formatSignedUsd(gainsAndLosses.year_to_date_capital_gains)}
            </span>
          </p>
        </div>

        {/* (4) Income & Fees */}
        <div className="card income-fees-container">
          <h3 className="card-title">Income & Fees</h3>

          <p>
            <strong>Income (earned)</strong>
            <span>
              {formatUsd(gainsAndLosses.income_earned)} (
              <em>{formatBtc(gainsAndLosses.income_btc)}</em>)
            </span>
          </p>
          <p>
            <strong>Interest (earned)</strong>
            <span>
              {formatUsd(gainsAndLosses.interest_earned)} (
              <em>{formatBtc(gainsAndLosses.interest_btc)}</em>)
            </span>
          </p>
          <p>
            <strong>Rewards (earned)</strong>
            <span>
              {formatUsd(gainsAndLosses.rewards_earned)} (
              <em>{formatBtc(gainsAndLosses.rewards_btc)}</em>)
            </span>
          </p>

          <hr />

          <p>
            <strong>Total Income</strong>
            <span>{formatUsd(gainsAndLosses.total_income)}</span>
          </p>

          <p>
            <strong>Gifts (received)</strong>
            <span>
              {formatUsd(gainsAndLosses.gifts_received)} (
              <em>{formatBtc(gainsAndLosses.gifts_btc)}</em>)
            </span>
          </p>
          <p className="gifts-note">
            <em>(not added to income or gains)</em>
          </p>

          <hr />

          <h4 className="card-subtitle">Fees</h4>
          <p>
            <strong>Fees (USD)</strong>
            <span>{formatUsd(gainsAndLosses.fees.USD)}</span>
          </p>
          <p>
            <strong>Fees (BTC)</strong>
            <span>{formatBtc(gainsAndLosses.fees.BTC)}</span>
          </p>

          {isPriceLoading ? (
            <p>
              <strong>Total Fees in USD (approx)</strong>
              <span>Loading...</span>
            </p>
          ) : currentBtcPrice !== null ? (
            <p>
              <strong>Total Fees in USD (approx)</strong>
              <span>
                {formatUsd(
                  gainsAndLosses.fees.USD + gainsAndLosses.fees.BTC * currentBtcPrice
                )}
              </span>
            </p>
          ) : (
            <p>
              <strong>Total Fees in USD</strong>
              <span>N/A</span>
            </p>
          )}
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
