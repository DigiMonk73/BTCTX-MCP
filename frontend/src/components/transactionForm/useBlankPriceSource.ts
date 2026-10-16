import { useEffect, useState } from "react";
import api from "../../api";
import { blankPriceSource, type PriceStatus } from "../../utils/priceStatus";

/**
 * Where a blank value's price comes from, in words for its hint (#208): ""
 * until the price status answers. The status asks nobody, only this BitcoinTX.
 */
export function useBlankPriceSource(): string {
  const [words, setWords] = useState("");
  useEffect(() => {
    api
      .get<PriceStatus>("/bitcoin/price/status")
      .then((res) => setWords(blankPriceSource(res.data)))
      .catch(() => undefined); // the hint keeps its first sentence
  }, []);
  return words;
}
