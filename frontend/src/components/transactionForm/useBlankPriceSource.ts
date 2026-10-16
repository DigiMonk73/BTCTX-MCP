import { useEffect, useState } from "react";
import api from "../../api";
import type { NetworkSettingsData } from "../../utils/priceSource";
import { blankDayPriceSource, blankPriceSource, type PriceStatus } from "../../utils/priceStatus";

/** Where a blank value's price comes from, in words for its hint: an hour's, or a day's (an inheritance's). */
export interface BlankPriceWords {
  hour: string;
  day: string;
}

/**
 * The hint's words (#208): "" until the price status and the saved choice
 * (its backup and Tor) answer. Both ask nobody, only this BitcoinTX.
 */
export function useBlankPriceSource(): BlankPriceWords {
  const [words, setWords] = useState<BlankPriceWords>({ hour: "", day: "" });
  useEffect(() => {
    Promise.all([api.get<PriceStatus>("/bitcoin/price/status"), api.get<NetworkSettingsData>("/settings/network")])
      .then(([status, settings]) => {
        const ctx = { backup: Boolean(settings.data.mempool_fallback), tor: Boolean(settings.data.proxy_url) };
        setWords({ hour: blankPriceSource(status.data, ctx), day: blankDayPriceSource(status.data, ctx) });
      })
      .catch(() => undefined); // the hint keeps its first sentence
  }, []);
  return words;
}
