import axios from "axios";
import React, { useEffect, useState } from "react";
import api from "../api";
import BtcPriceCard from "../components/dashboard/BtcPriceCard";
import IncomeFeesCard from "../components/dashboard/IncomeFeesCard";
import PortfolioOverview from "../components/dashboard/PortfolioOverview";
import RealizedGainsCard from "../components/dashboard/RealizedGainsCard";
import { NO_TOTALS, accountTotals, type AccountTotals, type LivePrice } from "../utils/dashboard";
import { parseGainsAndLosses } from "../utils/format";
import "../styles/dashboard.css";

const CARD_TITLES = ["Portfolio Overview", "Current Bitcoin Price", "Realized Gains/Losses (FIFO)", "Income & Fees"];

const Dashboard: React.FC = () => {
  const [balances, setBalances] = useState<AccountBalance[] | null>(null);
  const [totals, setTotals] = useState<AccountTotals>(NO_TOTALS);
  const [averageBtcCostBasis, setAverageBtcCostBasis] = useState<number | null>(null);
  const [gainsAndLosses, setGainsAndLosses] = useState<GainsAndLosses | null>(null);

  const [fetchError, setFetchError] = useState<string | null>(null);
  const [currentBtcPrice, setCurrentBtcPrice] = useState<number | null>(null);
  const [isPriceLoading, setIsPriceLoading] = useState(true);
  const [blockHeight, setBlockHeight] = useState<number | null>(null);
  // Settings → Privacy & network: no price source chosen, or prices off (503)
  const [pricesOff, setPricesOff] = useState(false);
  // The server's reason when there's no price (shown on hover)
  const [priceProblem, setPriceProblem] = useState<string | undefined>(undefined);

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
        // Shown as "Error", or "Prices off" when that is the owner's choice
        if (axios.isAxiosError(err) && err.response?.status === 503) setPricesOff(true);
        const detail = axios.isAxiosError(err) ? err.response?.data?.detail : undefined;
        if (typeof detail === "string") setPriceProblem(detail);
      })
      .finally(() => {
        setIsPriceLoading(false);
      });
  }, []);

  useEffect(() => {
    api
      .get("/bitcoin/blockheight")
      .then((res) => {
        if (res.data && res.data.height) {
          setBlockHeight(res.data.height);
        }
      })
      .catch(() => {
        // No block height: the card leaves it out
      });
  }, []);

  useEffect(() => {
    api
      .get<AverageCostBasis>("/calculations/average-cost-basis")
      .then((res) => {
        setAverageBtcCostBasis(res.data.averageCostBasis);
      })
      .catch(() => {
        // No average cost: the overview keeps showing "Loading..."
      });
  }, []);

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

  useEffect(() => {
    if (!balances) return;
    setTotals(accountTotals(balances));
  }, [balances]);

  useEffect(() => {
    api
      .get<GainsAndLossesRaw>("/calculations/gains-and-losses")
      .then((response) => {
        setGainsAndLosses(parseGainsAndLosses(response.data));
      })
      .catch((err) => {
        setFetchError(err instanceof Error ? err.message : "Failed to load gains/losses");
      });
  }, []);

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
          {CARD_TITLES.map((title) => (
            <div key={title} className="card dashboard-card-loading">
              <h3 className="card-title">{title}</h3>
              <div className="loading-row">
                <div className="spinner" /> Loading…
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  const price: LivePrice = { loading: isPriceLoading, value: currentBtcPrice, off: pricesOff, problem: priceProblem };
  return (
    <div className="dashboard">
      <div className="dashboard-grid">
        <PortfolioOverview totals={totals} averageCostBasis={averageBtcCostBasis} price={price} />
        <BtcPriceCard price={price} blockHeight={blockHeight} />
        <RealizedGainsCard gains={gainsAndLosses} />
        <IncomeFeesCard gains={gainsAndLosses} price={price} />
      </div>
    </div>
  );
};

export default Dashboard;
