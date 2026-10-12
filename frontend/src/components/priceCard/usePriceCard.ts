import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import api from "../../api";
import { getTaxTimezone } from "../../utils/taxTimezone";
import {
  formFromSettings,
  payloadFromForm,
  type NetworkSettingsData,
  type PriceForm,
} from "../../utils/priceSource";
import type { PriceStatus } from "../../utils/priceStatus";

/** Sent on window when the price choice is saved: the Dashboard and the
 * sidebar ask for their prices again, with no page reload (#149). */
export const PRICE_CHOICE_SAVED = "btctx:price-choice-saved";

const STATUS_EVERY_MS = 30_000; // asks this BitcoinTX only: the route never asks anyone

const EMPTY: PriceForm = { source: "", mempoolUrl: "", backup: false, tor: false, torUrl: "" };

export type FieldErrors = { mempoolUrl?: string; torUrl?: string };

/** Which field a refusal from the server is about, if one is. */
function fieldOf(detail: string): keyof FieldErrors | null {
  if (/mempool server|Mempool's address/i.test(detail)) return "mempoolUrl";
  if (/proxy|\.onion/i.test(detail)) return "torUrl";
  return null;
}

/** The card's data: the saved settings, the form, the status and the tax timezone. */
export function usePriceCard() {
  const [saved, setSaved] = useState<NetworkSettingsData | null>(null);
  const [form, setForm] = useState<PriceForm>(EMPTY);
  const [status, setStatus] = useState<PriceStatus | null>(null);
  const [timezone, setTimezone] = useState("UTC");
  const [errors, setErrors] = useState<FieldErrors>({});
  const [saving, setSaving] = useState(false);

  const loadStatus = useCallback(() => {
    api
      .get<PriceStatus>("/bitcoin/price/status")
      .then((res) => setStatus(res.data))
      .catch(() => undefined); // the line says "Loading…" until it comes
  }, []);

  useEffect(() => {
    api
      .get<NetworkSettingsData>("/settings/network")
      .then((res) => {
        setSaved(res.data);
        setForm(formFromSettings(res.data));
      })
      .catch(() => undefined);
    getTaxTimezone()
      .then((tz) => setTimezone(tz.timezone))
      .catch(() => undefined);
    loadStatus();
    const id = setInterval(() => {
      if (!document.hidden) loadStatus();
    }, STATUS_EVERY_MS);
    return () => clearInterval(id);
  }, [loadStatus]);

  const set = (patch: Partial<PriceForm>) => {
    setForm((f) => ({ ...f, ...patch }));
    setErrors({});
  };

  /** Save; true when saved. A refusal about a field shows under it, else it's returned. */
  const save = async (via: "first-run" | "settings"): Promise<{ ok: boolean; message?: string }> => {
    setSaving(true);
    try {
      const res = await api.put<NetworkSettingsData>("/settings/network", { ...payloadFromForm(form), via });
      setSaved(res.data);
      setForm(formFromSettings(res.data));
      loadStatus();
      window.dispatchEvent(new Event(PRICE_CHOICE_SAVED));
      return { ok: true };
    } catch (err) {
      const detail = axios.isAxiosError(err) ? err.response?.data?.detail : undefined;
      const message = typeof detail === "string" ? detail : "Could not save the choice.";
      const field = fieldOf(message);
      if (field) setErrors({ [field]: message });
      return { ok: false, message };
    } finally {
      setSaving(false);
    }
  };

  return { saved, form, set, status, timezone, errors, saving, save };
}
