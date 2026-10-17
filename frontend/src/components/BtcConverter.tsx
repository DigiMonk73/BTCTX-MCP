import React, { useState, useEffect, useCallback, useRef } from "react";
import axios from "axios";
import api from "../api";
import { noPriceReason, priceSourceShort, priceSourceWords, type NoPrice } from "../utils/dashboard";
import { clock } from "../utils/priceStatus";
import { browserTimezone } from "../utils/taxTimezone";
import { historyPriceUrl, satsFromBtc, satsFromUsd } from "../utils/converter";
import { btcText } from "../utils/format";
import { PRICE_CHOICE_SAVED } from "./priceCard/usePriceCard";
import AutoPriceRow, { type PriceFrom } from "./converter/AutoPriceRow";
import "../styles/converter.css";

type Mode = "manual" | "auto" | "date";

const HOURS = Array.from({ length: 24 }, (_, h) => h);

// What the converter says instead of a price (#145): never "$0.00"
const NO_PRICE_WORDS: Record<NoPrice | "loading" | "missing", string> = {
  loading: "…",
  waiting: "waiting for you",
  unchosen: "not chosen yet",
  off: "offline",
  invalid: "offline",
  tor: "no answer",
  none: "no answer",
  missing: "No price",
};
type Field = "USD" | "BTC" | "SATS" | null;

const BtcConverter: React.FC = () => {
  const [mode, setMode] = useState<Mode>("auto");
  const [btcPrice, setBtcPrice] = useState<number>(0);
  // Why there's no price, when there's none: never shown as "$0.00". "missing":
  // Date mode's day has none
  const [noPrice, setNoPrice] = useState<"loading" | NoPrice | "missing">("loading");
  // Where the price came from and when ("kraken", "mempool"; the live price only)
  const [answered, setAnswered] = useState<{ source?: string; at?: string } | null>(null);
  // Whether public sites are asked through Tor (null until the settings answer):
  // the source line waits for it, so it never shows without "through Tor" first
  const [throughTor, setThroughTor] = useState<boolean | null>(null);
  // Bumped by every mode switch and every typed price: an answer to an older
  // request (slow to arrive) is dropped instead of overwriting the price.
  const priceTicket = useRef(0);
  const fetchPrice = async (url: string) => {
    const ticket = priceTicket.current;
    let price = 0;
    let why: NoPrice | "missing" = "none";
    let from: { source?: string; at?: string } | null = null;
    try {
      const res = await api.get<LiveBtcPriceResponse>(url);
      if (res.data && typeof res.data.USD === "number") price = res.data.USD;
      from = { source: res.data?.source, at: res.data?.at };
    } catch (err) {
      // no price: 0, and why (backend/services/outbound.py's 503s are choices)
      const status = axios.isAxiosError(err) ? err.response?.status : undefined;
      why = url.includes("/history") ? "missing" : noPriceReason(status, axios.isAxiosError(err) ? err.response?.data?.detail : undefined);
    }
    if (ticket === priceTicket.current) {
      setBtcPrice(price);
      setNoPrice(why);
      setAnswered(from);
    }
  };

  /** Auto's source line: "Kraken · 2:04 pm" (the Dashboard's words on hover), once the settings say whether through Tor. */
  const priceFrom = (): PriceFrom | null => {
    if (btcPrice <= 0 || !answered?.source || throughTor === null) return null;
    const at = answered.at ? ` · ${clock(answered.at)}` : "";
    return {
      short: `${priceSourceShort(answered.source, throughTor)}${at}`,
      full: `${priceSourceWords(answered.source, throughTor)}${at}`,
    };
  };

  const priceText = () =>
    btcPrice > 0
      ? "$" + btcPrice.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
      : NO_PRICE_WORDS[noPrice];

  // Date mode's day, and its hour on this device's clock, as the
  // transaction form's Date & Time is (#260; "": the day's 00:00 UTC price)
  const [selectedDate, setSelectedDate] = useState<string>("");
  const [selectedHour, setSelectedHour] = useState<string>("");
  const timezone = browserTimezone();

  const [usdValue, setUsdValue] = useState<string>("");
  const [btcValue, setBtcValue] = useState<string>("");
  const [satsValue, setSatsValue] = useState<string>("");

  // The field typed in last: the other two are worked out from it
  const [lastChangedField, setLastChangedField] = useState<Field>(null);

  // BTC to the satoshi as plain digits (btcText: 1 sat is "0.00000001", never "1e-8"), USD to the cent.
  const roundUsd = (num: number) => Math.round(num * 100) / 100;

  // Whether public sites go through Tor, for the source line: read again when a
  // choice is saved, unknown meanwhile (only the newest read counts)
  useEffect(() => {
    let round = 0;
    const read = () => {
      const mine = ++round;
      api
        .get<{ proxy_url?: string | null }>("/settings/network")
        .then((res) => mine === round && setThroughTor(Boolean(res.data.proxy_url)))
        .catch(() => mine === round && setThroughTor(false));
    };
    const again = () => {
      setThroughTor(null);
      read();
    };
    read();
    window.addEventListener(PRICE_CHOICE_SAVED, again);
    return () => window.removeEventListener(PRICE_CHOICE_SAVED, again);
  }, []);

  // Auto mode: the live price, every 2 minutes
  useEffect(() => {
    if (mode !== "auto") return;

    const fetchLivePrice = () => fetchPrice("/bitcoin/price");
    // A price choice just saved: ask again now, no page reload (#145, #149). An answer
    // for the old choice still on its way is dropped (#327), and until the new one the
    // sidebar says "…", as the Dashboard does: the old price never takes the new source
    const askAgain = () => {
      priceTicket.current += 1;
      setBtcPrice(0);
      setNoPrice("loading");
      setAnswered(null);
      fetchLivePrice();
    };

    fetchLivePrice();
    // No asking while this tab isn't being looked at.
    const intervalId = setInterval(() => {
      if (!document.hidden) fetchLivePrice();
    }, 120_000);
    window.addEventListener(PRICE_CHOICE_SAVED, askAgain);
    return () => {
      clearInterval(intervalId);
      window.removeEventListener(PRICE_CHOICE_SAVED, askAgain);
    };
  }, [mode]);

  // Date mode: that day's price, or the hour's (#145). This BitcoinTX only: it
  // looks it up in its stored history, and no outside request names the day
  useEffect(() => {
    if (mode !== "date") return; // the other modes' own requests keep their ticket
    priceTicket.current += 1; // an answer for an earlier day or hour, or a cleared one, is dropped
    if (!selectedDate) return;

    setBtcPrice(0);
    const url = historyPriceUrl(selectedDate, selectedHour);
    setNoPrice(url ? "loading" : "missing");
    if (url) fetchPrice(url);
  }, [mode, selectedDate, selectedHour]);

  // Manual mode starts from the live price, fetched once
  const fetchManualPriceOnce = () => fetchPrice("/bitcoin/price");

  const handleModeChange = (newMode: Mode) => {
    // The mode in use, chosen again: nothing to change. Clearing the price here
    // left Auto at "…" until its next poll, since Auto asks only on a change (#328)
    if (newMode === mode) return;
    priceTicket.current += 1;
    setMode(newMode);
    setSelectedDate("");
    setSelectedHour("");
    setBtcPrice(0);
    setNoPrice(newMode === "date" ? "none" : "loading");

    if (newMode === "manual") {
      fetchManualPriceOnce();
    }
  };

  // A typed value converts the other two fields. updateLastField is false
  // when a new price converts them again.
  const handleUsdChange = useCallback(
    (value: string, updateLastField = true) => {
      setUsdValue(value);
      // One count, and the BTC field written from it, so the two agree (#451)
      const sats = satsFromUsd(parseFloat(value) || 0, btcPrice);

      setBtcValue(sats === null ? "" : btcText(sats / 100_000_000));
      setSatsValue(sats === null ? "" : sats.toString());

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
      const sats = btcNum ? satsFromBtc(value) : null;

      setUsdValue(usdNum ? roundUsd(usdNum).toString() : "");
      setSatsValue(sats === null ? "" : sats.toString());

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

      setBtcValue(btcNum ? btcText(btcNum) : "");
      setUsdValue(usdNum ? roundUsd(usdNum).toString() : "");

      if (updateLastField) {
        setLastChangedField("SATS");
      }
    },
    [btcPrice]
  );

  // A new price converts again from the field typed in last.
  useEffect(() => {
    // If there's nothing typed yet, do nothing. Without a price the USD side
    // empties (BTC and sats still convert), rather than keeping an old figure.
    if (!usdValue && !btcValue && !satsValue) return;

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

  return (
    <div className="converter">
      <div className="converter-title">Sats Converter</div>

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

      {mode === "manual" && (
        <div className="manual-price-row price-mode-row">
          <label htmlFor="manualPrice" className="field-label">BTC price (USD)</label>
          <input
            id="manualPrice"
            className="input input-sm"
            type="number"
            value={btcPrice}
            onChange={(e) => {
              const val = parseFloat(e.target.value) || 0;
              priceTicket.current += 1; // the seed price may still be on its way
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

      {mode === "auto" && (
        <AutoPriceRow
          text={priceText()}
          why={btcPrice > 0 ? null : noPrice}
          from={priceFrom()}
          onTypeAPrice={() => handleModeChange("manual")}
        />
      )}

      {mode === "date" && (
        <div className="date-price-row price-mode-row">
          {/* The day's price beside the label, so this mode is as tall as the others */}
          <div className="date-label-row">
            <label htmlFor="datePicker" className="field-label">Select date</label>
            {selectedDate && <span className="btc-price">{priceText()}</span>}
          </div>
          <div className="date-input-row">
            <input
              id="datePicker"
              className="input input-sm"
              type="date"
              value={selectedDate}
              onChange={(e) => setSelectedDate(e.target.value)}
            />
            <select
              className="input input-sm date-hour"
              aria-label="Hour"
              title={`The hour on this device's clock (${timezone})`}
              value={selectedHour}
              onChange={(e) => setSelectedHour(e.target.value)}
            >
              <option value="">Day</option>
              {HOURS.map((h) => (
                <option key={h} value={String(h)}>
                  {`${String(h).padStart(2, "0")}:00`}
                </option>
              ))}
            </select>
          </div>
        </div>
      )}

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
