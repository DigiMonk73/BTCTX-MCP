import React, { useState } from "react";
import api from "../../api";
import { useToast } from "../../contexts/useToast";
import { detailOr } from "../../utils/apiError";
import {
  CHANGE_LATER,
  IF_NO,
  IF_YES,
  NO_LABEL,
  QUESTION,
  QUESTION_WHY,
  YES_LABEL,
  answerOf,
  answeredWords,
  changeLabel,
  questionOpen,
} from "../../utils/historyWithoutTor";
import type { NetworkSettingsData } from "../../utils/priceSource";
import type { PriceStatus } from "../../utils/priceStatus";

const ROUTE = "/settings/network/history-without-tor";

interface Props {
  saved: NetworkSettingsData;
  status: PriceStatus | null;
  /** Where it's shown: the Dashboard asks only; Settings also shows the answer, to change it. */
  via: "dashboard" | "settings";
  onChange: (settings: NetworkSettingsData) => void;
}

/**
 * "Download the price history once without Tor?" (#241): asked once Bitstamp
 * has refused through Tor and until it's answered; in Settings, the recorded
 * answer and a button to change it. Login only on the server, never the AI key.
 */
const HistoryWithoutTor: React.FC<Props> = ({ saved, status, via, onChange }) => {
  const toast = useToast();
  const [busy, setBusy] = useState(false);

  const answer = async (value: "yes" | "no") => {
    setBusy(true);
    try {
      onChange((await api.put<NetworkSettingsData>(ROUTE, { answer: value, via })).data);
      toast.success(value === "yes" ? "Downloading the price history without Tor." : "Kept on Tor: nothing goes without it.");
    } catch (err) {
      toast.error(detailOr(err, "Could not save the answer."));
    } finally {
      setBusy(false);
    }
  };

  if (questionOpen(saved, status)) {
    return (
      <div className="price-question" role="group" aria-labelledby={`history-without-tor-${via}`}>
        <p id={`history-without-tor-${via}`} className="price-question-title">
          {QUESTION}
        </p>
        <p className="price-help">{QUESTION_WHY}</p>
        <p className="price-help">{IF_YES}</p>
        <p className="price-help">{IF_NO}</p>
        <div className="price-actions">
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => answer("yes")} disabled={busy}>
            {YES_LABEL}
          </button>
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => answer("no")} disabled={busy}>
            {NO_LABEL}
          </button>
        </div>
        <p className="price-help">{CHANGE_LATER}</p>
      </div>
    );
  }
  const words = via === "settings" ? answeredWords(saved) : null;
  if (!words) return null;
  const given = answerOf(saved);
  return (
    <div className="price-trust">
      <p className="price-help">{words}</p>
      <button
        type="button"
        className="btn btn-secondary btn-sm"
        onClick={() => answer(given === "yes" ? "no" : "yes")}
        disabled={busy}
      >
        {changeLabel(given)}
      </button>
    </div>
  );
};

export default HistoryWithoutTor;
