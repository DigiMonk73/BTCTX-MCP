// FILE: frontend/src/components/PriceSourcePrompt.tsx
//
// A fresh install contacts nothing until the owner chooses where prices come
// from. Until then this panel sits at the top of every page. The same choice
// stays in Settings → Privacy & network.

import React, { useEffect, useState } from "react";
import axios from "axios";
import api from "../api";
import { useToast } from "../contexts/useToast";
import {
  MEMPOOL_PLACEHOLDER,
  NetworkSettingsData,
  PRICE_SOURCES,
  PriceSource,
} from "../utils/priceSource";

const PriceSourcePrompt: React.FC = () => {
  const toast = useToast();
  const [settings, setSettings] = useState<NetworkSettingsData | null>(null);
  const [source, setSource] = useState<PriceSource | "">("");
  const [mempoolUrl, setMempoolUrl] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api
      .get<NetworkSettingsData>("/settings/network")
      .then((res) => setSettings(res.data))
      .catch(() => undefined);
  }, []);

  if (settings?.price_source !== "unset") return null;

  const save = async () => {
    setSaving(true);
    try {
      await api.put<NetworkSettingsData>("/settings/network", {
        price_source: source,
        mempool_url: source === "mempool" ? mempoolUrl.trim() || null : null,
        mempool_fallback: false,
        proxy_url: null,
      });
      // Prices on the page were asked before the choice: load them again.
      window.location.reload();
    } catch (err) {
      const detail = axios.isAxiosError(err) ? err.response?.data?.detail : undefined;
      toast.error(typeof detail === "string" ? detail : "Could not save the choice.");
      setSaving(false);
    }
  };

  return (
    <section className="price-source-prompt card" role="region" aria-label="Choose a price source">
      <h2>Where should BitcoinTX get Bitcoin prices?</h2>
      <p className="price-source-lede">
        Nothing is contacted until you choose. You can change it any time in Settings → Privacy
        &amp; Network, which also has a proxy option (Tor) for the public sites.
      </p>
      <div className="price-source-options" role="radiogroup" aria-label="Price source">
        {PRICE_SOURCES.map((s) => (
          <label key={s.value} className="price-source-option">
            <input
              type="radio"
              name="price-source"
              value={s.value}
              checked={source === s.value}
              onChange={() => setSource(s.value)}
            />
            <span>
              <strong>{s.label}</strong>
              <span className="price-source-help">{s.help}</span>
            </span>
          </label>
        ))}
      </div>
      {source === "mempool" && (
        <input
          className="input price-source-url"
          type="url"
          aria-label="Your mempool server"
          placeholder={MEMPOOL_PLACEHOLDER}
          value={mempoolUrl}
          onChange={(e) => setMempoolUrl(e.target.value)}
        />
      )}
      <button
        type="button"
        className="btn btn-primary"
        onClick={save}
        disabled={saving || source === "" || (source === "mempool" && !mempoolUrl.trim())}
      >
        {saving ? "Saving..." : "Use this"}
      </button>
    </section>
  );
};

export default PriceSourcePrompt;
