import React, { useEffect, useState } from "react";
import api from "../api";
import BtcPriceCard from "../components/dashboard/BtcPriceCard";
import IncomeFeesCard from "../components/dashboard/IncomeFeesCard";
import PriceSourceCard from "../components/priceCard/PriceSourceCard";
import { PRICE_CHOICE_SAVED } from "../components/priceCard/usePriceCard";
import PortfolioOverview from "../components/dashboard/PortfolioOverview";
import RealizedGainsCard from "../components/dashboard/RealizedGainsCard";
import { NO_TOTALS, accountTotals, type AccountTotals } from "../utils/dashboard";
import { useLivePrice } from "../components/dashboard/useLivePrice";
import { getTaxTimezone } from "../utils/taxTimezone";
import { parseGainsAndLosses } from "../utils/format";
import "../styles/dashboard.css";

const CARD_TITLES = ["Portfolio Overview", "Current Bitcoin Price", "Realized Gains/Losses (FIFO)", "Income & Fees"];

const Dashboard: React.FC = () => {
  const [balances, setBalances] = useState<AccountBalance[] | null>(null);
  const [totals, setTotals] = useState<AccountTotals>(NO_TOTALS);
  const [averageBtcCostBasis, setAverageBtcCostBasis] = useState<number | null>(null);
  const [gainsAndLosses, setGainsAndLosses] = useState<GainsAndLosses | null>(null);

  const [fetchError, setFetchError] = useState<string | null>(null);
  const [blockHeight, setBlockHeight] = useState<number | null>(null);
  // No price source chosen yet, or one to confirm (2.9): the question sits at the top (#145)
  const [unchosen, setUnchosen] = useState(false);
  // Bumped when the price choice is saved: prices are asked again, no reload (#149)
  const [priceRound, setPriceRound] = useState(0);

  useEffect(() => {
    const again = () => setPriceRound((n) => n + 1);
    window.addEventListener(PRICE_CHOICE_SAVED, again);
    return () => window.removeEventListener(PRICE_CHOICE_SAVED, again);
  }, []);

  useEffect(() => {
    api
      .get<{ price_source: string; managed?: boolean; confirmed?: boolean }>("/settings/network")
      .then((res) =>
        setUnchosen(!res.data.managed && (res.data.price_source === "unset" || res.data.confirmed === false)),
      )
      .catch(() => undefined);
  }, [priceRound]);

  const price = useLivePrice(priceRound);
  const [timezone, setTimezone] = useState("UTC");

  useEffect(() => {
    getTaxTimezone()
      .then((tz) => setTimezone(tz.timezone))
      .catch(() => undefined);
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

  return (
    <div className="dashboard">
      {unchosen && <PriceSourceCard variant="first-run" />}
      <div className="dashboard-grid">
        <PortfolioOverview totals={totals} averageCostBasis={averageBtcCostBasis} price={price} />
        <BtcPriceCard price={price} blockHeight={blockHeight} timezone={timezone} />
        <RealizedGainsCard gains={gainsAndLosses} />
        <IncomeFeesCard gains={gainsAndLosses} price={price} />
      </div>
    </div>
  );
};

export default Dashboard;
