import { useEffect, useState } from "react";
import axios from "axios";
import api from "../../api";
import { noPriceReason, type LivePrice } from "../../utils/dashboard";

const LOADING: LivePrice = { loading: true, value: null, off: false };

/**
 * The live price as the Dashboard shows it, asked again whenever `round`
 * changes (a price choice saved, #149): its value, where it came from and
 * when, or why there's none (never $0.00).
 */
export function useLivePrice(round: number): LivePrice {
  const [price, setPrice] = useState<LivePrice>(LOADING);

  useEffect(() => {
    let current = true;
    setPrice(LOADING);
    api
      .get<LiveBtcPriceResponse>("/bitcoin/price")
      .then((res) => {
        const usd = res.data?.USD;
        if (current) {
          setPrice({ loading: false, value: usd ? usd : null, off: false, source: res.data?.source, at: res.data?.at });
        }
      })
      .catch((err) => {
        const status = axios.isAxiosError(err) ? err.response?.status : undefined;
        const detail = axios.isAxiosError(err) ? err.response?.data?.detail : undefined;
        const why = noPriceReason(status, detail);
        if (current) {
          setPrice({
            loading: false, value: null, off: why === "off", waiting: why === "waiting", unchosen: why === "unchosen",
            problem: typeof detail === "string" ? detail : undefined,
          });
        }
      });
    return () => {
      current = false;
    };
  }, [round]);

  return price;
}
