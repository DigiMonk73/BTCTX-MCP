import React from "react";
import { questionOpen, refusedWords } from "../../utils/historyWithoutTor";
import HistoryWithoutTor from "../priceCard/HistoryWithoutTor";
import { usePriceCard } from "../priceCard/usePriceCard";
import "../../styles/priceCard.css";

/**
 * The price card's question on the Dashboard (#241): the first-run card has
 * gone by the time Bitstamp refuses through Tor, so the question shows here,
 * at the top, until it's answered (also in Settings → Privacy & network).
 */
const HistoryQuestionCard: React.FC = () => {
  const { saved, status, applied } = usePriceCard();
  if (!saved || !status || !questionOpen(saved, status)) return null;
  return (
    <section className="price-card card first-run" aria-labelledby="history-question-title">
      <h2 id="history-question-title" className="price-card-title">
        Bitcoin price history
      </h2>
      <p className="price-history-text">
        <span aria-hidden="true">▲ </span>
        {refusedWords(status)}
      </p>
      <HistoryWithoutTor saved={saved} status={status} via="dashboard" onChange={applied} />
    </section>
  );
};

export default HistoryQuestionCard;
