import React, { useEffect, useState } from "react";
import api from "../api";
import BtcPriceCard from "../components/dashboard/BtcPriceCard";
import HistoryQuestionCard from "../components/dashboard/HistoryQuestionCard";
import IncomeFeesCard from "../components/dashboard/IncomeFeesCard";
import LoadingCard from "../components/dashboard/LoadingCard";
import PriceSourceCard from "../components/priceCard/PriceSourceCard";
import { PRICE_CHOICE_SAVED } from "../components/priceCard/usePriceCard";
import PortfolioOverview from "../components/dashboard/PortfolioOverview";
import RealizedGainsCard from "../components/dashboard/RealizedGainsCard";
import { useLivePrice } from "../components/dashboard/useLivePrice";
import { parseGainsAndLosses } from "../utils/format";
import "../styles/dashboard.css";

const GRID_TITLES = ["Portfolio Overview", "Current Bitcoin Price", "Realized Gains/Losses (FIFO)", "Income & Fees"];

const Dashboard: React.FC = () => {
  const [balances, setBalances] = useState<AccountBalance[] | null>(null);
  const [averageBtcCostBasis, setAverageBtcCostBasis] = useState<number | null>(null);
  const [gainsAndLosses, setGainsAndLosses] = useState<GainsAndLosses | null>(null);

  const [fetchError, setFetchError] = useState<string | null>(null);
  const [blockHeight, setBlockHeight] = useState<number | null>(null);
  // No price source chosen yet, or one to confirm (2.9): the question sits at the top (#145)
  const [unchosen, setUnchosen] = useState(false);
  // Bumped when the price choice is saved: prices are asked again, no reload (#149)
  const [priceRound, setPriceRound] = useState(0);
  // null until the settings answer: the source line waits for it, so it
  // never shows without "through Tor" first
  const [throughTor, setThroughTor] = useState<boolean | null>(null);

  useEffect(() => {
    const again = () => setPriceRound((n) => n + 1);
    window.addEventListener(PRICE_CHOICE_SAVED, again);
    return () => window.removeEventListener(PRICE_CHOICE_SAVED, again);
  }, []);

  useEffect(() => {
    api
      .get<{ price_source: string; managed?: boolean; confirmed?: boolean; proxy_url?: string | null }>(
        "/settings/network",
      )
      .then((res) => {
        setUnchosen(!res.data.managed && (res.data.price_source === "unset" || res.data.confirmed === false));
        setThroughTor(Boolean(res.data.proxy_url));
      })
      .catch(() => setThroughTor(false));
  }, [priceRound]);

  const live = useLivePrice(priceRound);
  const price = { ...live, source: throughTor === null ? undefined : live.source, throughTor: Boolean(throughTor) };
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
  }, [priceRound]);

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
          {GRID_TITLES.map((title) => <LoadingCard key={title} title={title} />)}
        </div>
      </div>
    );
  }

  return (
    <div className="dashboard">
      {unchosen ? <PriceSourceCard variant="first-run" /> : <HistoryQuestionCard />}
      <div className="dashboard-grid">
        <PortfolioOverview balances={balances} averageCostBasis={averageBtcCostBasis} price={price} />
        <BtcPriceCard price={price} blockHeight={blockHeight} />
        <RealizedGainsCard gains={gainsAndLosses} />
        <IncomeFeesCard gains={gainsAndLosses} price={price} />
      </div>
    </div>
  );
};

export default Dashboard;
