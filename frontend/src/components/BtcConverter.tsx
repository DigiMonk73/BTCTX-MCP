import React, { useState, useEffect, useCallback } from "react";
import api from "../api";
import "../styles/converter.css";

// Types LiveBtcPriceResponse is defined in types/global.d.ts

type Mode = "manual" | "auto" | "date";
type Field = "USD" | "BTC" | "SATS" | null;

const BtcConverter: React.FC = () => {
  // ---------------------------------------------------------------------------
  // 1) Mode & Price
  // ---------------------------------------------------------------------------
  const [mode, setMode] = useState<Mode>("auto");
  const [btcPrice, setBtcPrice] = useState<number>(0);

  // For date mode
  const [selectedDate, setSelectedDate] = useState<string>("");

  // ---------------------------------------------------------------------------
  // 2) Fields & "last-changed" tracking
  // ---------------------------------------------------------------------------
  const [usdValue, setUsdValue] = useState<string>("");
  const [btcValue, setBtcValue] = useState<string>("");
  const [satsValue, setSatsValue] = useState<string>("");

  // Which field the user last typed in (USD, BTC, or SATS)?
  const [lastChangedField, setLastChangedField] = useState<Field>(null);

  // Small helper to round BTC to 5 decimal places
  // BTC to the satoshi (8 decimals), USD to the cent.
  // As a plain decimal: 1 sat is "0.00000001", never "1e-8".
  const roundBtc = (num: number) => num.toFixed(8).replace(/\.?0+$/, "");
  const roundUsd = (num: number) => Math.round(num * 100) / 100;

  // ---------------------------------------------------------------------------
  // 3) Auto Mode: Fetch live price periodically
  // ---------------------------------------------------------------------------
  useEffect(() => {
    if (mode !== "auto") return;

    const fetchLivePrice = async () => {
      try {
        const res = await api.get<LiveBtcPriceResponse>("/bitcoin/price");
        if (res.data && typeof res.data.USD === "number") {
          setBtcPrice(res.data.USD);
        } else {
          setBtcPrice(0);
        }
      } catch {
        setBtcPrice(0);
      }
    };

    fetchLivePrice();
    const intervalId = setInterval(fetchLivePrice, 120_000);
    return () => clearInterval(intervalId);
  }, [mode]);

  // ---------------------------------------------------------------------------
  // 4) Date Mode: Fetch historical price
  // ---------------------------------------------------------------------------
  useEffect(() => {
    if (mode !== "date" || !selectedDate) return;

    const fetchHistoricalPrice = async () => {
      try {
        const res = await api.get<LiveBtcPriceResponse>(
          `/bitcoin/price/history?date=${selectedDate}`
        );
        if (res.data && typeof res.data.USD === "number") {
          setBtcPrice(res.data.USD);
        } else {
          setBtcPrice(0);
        }
      } catch {
        setBtcPrice(0);
      }
    };

    fetchHistoricalPrice();
  }, [mode, selectedDate]);

  // ---------------------------------------------------------------------------
  // 5) Manual Mode: fetch once to seed the price
  // ---------------------------------------------------------------------------
  const fetchManualPriceOnce = async () => {
    try {
      const res = await api.get<LiveBtcPriceResponse>("/bitcoin/price");
      if (res.data && typeof res.data.USD === "number") {
        setBtcPrice(res.data.USD);
      } else {
        setBtcPrice(0);
      }
    } catch {
      setBtcPrice(0);
    }
  };

  // ---------------------------------------------------------------------------
  // 6) Mode Switch
  // ---------------------------------------------------------------------------
  const handleModeChange = (newMode: Mode) => {
    setMode(newMode);
    setSelectedDate("");

    if (newMode === "manual") {
      fetchManualPriceOnce();
    }
  };

  // ---------------------------------------------------------------------------
  // 7) Conversion Handlers (stable via useCallback)
  //    - The second param, updateLastField, is false when we auto-recalc.
  // ---------------------------------------------------------------------------
  const handleUsdChange = useCallback(
    (value: string, updateLastField = true) => {
      setUsdValue(value);
      const usdNum = parseFloat(value) || 0;
      const btcNum = btcPrice ? usdNum / btcPrice : 0;
      const satsNum = btcNum * 100_000_000;

      setBtcValue(btcNum ? roundBtc(btcNum) : "");
      setSatsValue(satsNum ? Math.floor(satsNum).toString() : "");

      if (updateLastField) {
        setLastChangedField("USD");
      }
    },
    [btcPrice]
  );

  const handleBtcChange = useCallback(
    (value: string, updateLastField = true) => {
      setBtcValue(value);
      const btcNum = parseFloat(value) || 0;
      const usdNum = btcNum * btcPrice;
      const satsNum = btcNum * 100_000_000;

      setUsdValue(usdNum ? roundUsd(usdNum).toString() : "");
      setSatsValue(satsNum ? Math.floor(satsNum).toString() : "");

      if (updateLastField) {
        setLastChangedField("BTC");
      }
    },
    [btcPrice]
  );

  const handleSatsChange = useCallback(
    (value: string, updateLastField = true) => {
      setSatsValue(value);
      const satsNum = parseFloat(value) || 0;
      const btcNum = satsNum / 100_000_000;
      const usdNum = btcNum * btcPrice;

      setBtcValue(btcNum ? roundBtc(btcNum) : "");
      setUsdValue(usdNum ? roundUsd(usdNum).toString() : "");

      if (updateLastField) {
        setLastChangedField("SATS");
      }
    },
    [btcPrice]
  );

  // ---------------------------------------------------------------------------
  // 8) If btcPrice changes, recalc from whichever field was last typed
  //    to auto-update the others.
  // ---------------------------------------------------------------------------
  useEffect(() => {
    // If there's nothing typed yet, do nothing
    if (!usdValue && !btcValue && !satsValue) return;
    if (btcPrice === 0) return;

    if (lastChangedField === "USD" && usdValue) {
      handleUsdChange(usdValue, false);
    } else if (lastChangedField === "BTC" && btcValue) {
      handleBtcChange(btcValue, false);
    } else if (lastChangedField === "SATS" && satsValue) {
      handleSatsChange(satsValue, false);
    }
  }, [
    btcPrice,
    usdValue,
    btcValue,
    satsValue,
    lastChangedField,
    handleUsdChange,
    handleBtcChange,
    handleSatsChange,
  ]);

  // ---------------------------------------------------------------------------
  // 9) Render
  // ---------------------------------------------------------------------------
  return (
    <div className="converter">
      <div className="converter-title">Sats Converter</div>

      {/* Three mode buttons */}
      <div className="segmented price-toggle">
        <button
          type="button"
          className={mode === "manual" ? "active" : undefined}
          aria-pressed={mode === "manual"}
          onClick={() => handleModeChange("manual")}
        >
          Manual
        </button>
        <button
          type="button"
          className={mode === "auto" ? "active" : undefined}
          aria-pressed={mode === "auto"}
          onClick={() => handleModeChange("auto")}
        >
          Auto
        </button>
        <button
          type="button"
          className={mode === "date" ? "active" : undefined}
          aria-pressed={mode === "date"}
          onClick={() => handleModeChange("date")}
        >
          Date
        </button>
      </div>

      {/* Manual mode: editable price input */}
      {mode === "manual" && (
        <div className="manual-price-row">
          <label htmlFor="manualPrice" className="field-label">BTC price (USD)</label>
          <input
            id="manualPrice"
            className="input input-sm"
            type="number"
            value={btcPrice}
            onChange={(e) => {
              const val = parseFloat(e.target.value) || 0;
              setBtcPrice(val);

              // Re-run the last-changed field’s conversion
              if (lastChangedField === "USD" && usdValue) {
                handleUsdChange(usdValue, false);
              } else if (lastChangedField === "BTC" && btcValue) {
                handleBtcChange(btcValue, false);
              } else if (lastChangedField === "SATS" && satsValue) {
                handleSatsChange(satsValue, false);
              }
            }}
          />
        </div>
      )}

      {/* Auto mode: show live price */}
      {mode === "auto" && (
        <div className="auto-price-row">
          <p className="btc-price">
            BTC Price: $
            {btcPrice.toLocaleString(undefined, {
              minimumFractionDigits: 2,
              maximumFractionDigits: 2,
            })}
          </p>
        </div>
      )}

      {/* Date mode: date picker and historical price */}
      {mode === "date" && (
        <div className="date-price-row">
          <div className="date-input-row">
            <label htmlFor="datePicker" className="field-label">Select date</label>
            <input
              id="datePicker"
            className="input input-sm"
              type="date"
              value={selectedDate}
              onChange={(e) => setSelectedDate(e.target.value)}
            />
          </div>
          <p className="btc-price">
            BTC Price: $
            {btcPrice.toLocaleString(undefined, {
              minimumFractionDigits: 2,
              maximumFractionDigits: 2,
            })}
          </p>
        </div>
      )}

      {/* Conversion fields */}
      <div className="converter-row">
        <label className="field-label" htmlFor="usdInput">USD</label>
        <input
          id="usdInput"
          className="input"
          type="number"
          value={usdValue}
          onChange={(e) => handleUsdChange(e.target.value)}
        />
      </div>
      <div className="converter-row">
        <label className="field-label" htmlFor="btcInput">BTC</label>
        <input
          id="btcInput"
          className="input"
          type="number"
          value={btcValue}
          onChange={(e) => handleBtcChange(e.target.value)}
        />
      </div>
      <div className="converter-row">
        <label className="field-label" htmlFor="satsInput">Sats</label>
        <input
          id="satsInput"
          className="input"
          type="number"
          value={satsValue}
          onChange={(e) => handleSatsChange(e.target.value)}
        />
      </div>
    </div>
  );
};

export default BtcConverter;
