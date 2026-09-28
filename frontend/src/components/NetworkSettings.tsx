import React, { useEffect, useState } from "react";
import axios from "axios";
import api from "../api";
import { useToast } from "../contexts/useToast";
import {
  MANAGED_NOTE,
  MEMPOOL_PLACEHOLDER,
  NetworkSettingsData,
  PRICE_SOURCES,
  PriceSource,
} from "../utils/priceSource";

/**
 * Settings → Privacy & network (backend/services/outbound.py): where prices
 * and the block height come from (off, public sites, or the owner's own
 * mempool server, optionally falling back to the public sites), and a proxy
 * such as Tor for requests to public sites. Read-only when the server sets
 * them (StartOS's Price Source & Privacy action).
 */
const NetworkSettings: React.FC = () => {
  const toast = useToast();
  const [saved, setSaved] = useState<NetworkSettingsData | null>(null);
  const [source, setSource] = useState<PriceSource | "">("");
  const [mempoolUrl, setMempoolUrl] = useState("");
  const [fallback, setFallback] = useState(false);
  const [proxyUrl, setProxyUrl] = useState("");
  const [saving, setSaving] = useState(false);

  const show = (data: NetworkSettingsData) => {
    setSaved(data);
    setSource(data.price_source === "unset" ? "" : data.price_source);
    setMempoolUrl(data.mempool_url ?? "");
    setFallback(data.mempool_fallback);
    setProxyUrl(data.proxy_url ?? "");
  };

  useEffect(() => {
    api
      .get<NetworkSettingsData>("/settings/network")
      .then((res) => show(res.data))
      .catch(() => undefined);
  }, []);

  const changed =
    saved !== null &&
    source !== "" &&
    (source !== saved.price_source ||
      mempoolUrl.trim() !== (saved.mempool_url ?? "") ||
      fallback !== saved.mempool_fallback ||
      proxyUrl.trim() !== (saved.proxy_url ?? ""));

  const save = async () => {
    setSaving(true);
    try {
      const res = await api.put<NetworkSettingsData>("/settings/network", {
        price_source: source,
        mempool_url: mempoolUrl.trim() || null,
        mempool_fallback: fallback,
        proxy_url: proxyUrl.trim() || null,
      });
      show(res.data);
      toast.success("Privacy & network settings saved.");
    } catch (err) {
      const detail = axios.isAxiosError(err) ? err.response?.data?.detail : undefined;
      toast.error(typeof detail === "string" ? detail : "Could not save the settings.");
    } finally {
      setSaving(false);
    }
  };

  const chosen = PRICE_SOURCES.find((s) => s.value === source);
  const managed = saved?.managed === true;

  return (
    <div className="settings-section" role="region" aria-label="Privacy & network">
      <h3 className="section-title">Privacy &amp; Network</h3>
      {managed && <p className="settings-note">{MANAGED_NOTE}</p>}
      <div className="settings-option stacked">
        <div className="option-info">
          <label className="settings-option-title" htmlFor="net-price-source">
            Price source
          </label>
          <p className="settings-option-subtitle">
            {chosen
              ? chosen.help
              : "Not chosen yet: nothing is contacted until you pick one."}
          </p>
        </div>
        <select
          id="net-price-source"
          className="input"
          value={source}
          disabled={managed}
          onChange={(e) => setSource(e.target.value as PriceSource)}
        >
          {source === "" && (
            <option value="" disabled>
              Choose…
            </option>
          )}
          {PRICE_SOURCES.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </select>
      </div>
      {source === "mempool" && (
        <>
          <div className="settings-option stacked">
            <div className="option-info">
              <label className="settings-option-title" htmlFor="net-mempool-url">
                Your mempool server
              </label>
              <p className="settings-option-subtitle">
                Its address, e.g. {MEMPOOL_PLACEHOLDER}, a StartOS address, or an .onion (reached
                through the proxy below).
              </p>
            </div>
            <input
              id="net-mempool-url"
              className="input"
              type="url"
              placeholder={MEMPOOL_PLACEHOLDER}
              value={mempoolUrl}
              disabled={managed}
              onChange={(e) => setMempoolUrl(e.target.value)}
            />
          </div>
          <div className="settings-option">
            <div className="option-info">
              <label className="settings-option-title" htmlFor="net-mempool-fallback">
                Fall back to public price sites
              </label>
              <p className="settings-option-subtitle">
                When your mempool server doesn&apos;t answer, or doesn&apos;t have a past
                day&apos;s price, ask the public sites instead. Off: nothing goes to a public site.
              </p>
            </div>
            <input
              id="net-mempool-fallback"
              type="checkbox"
              checked={fallback}
              disabled={managed}
              onChange={(e) => setFallback(e.target.checked)}
            />
          </div>
        </>
      )}
      <div className="settings-option stacked">
        <div className="option-info">
          <label className="settings-option-title" htmlFor="net-proxy-url">
            Proxy for public sites
          </label>
          <p className="settings-option-subtitle">
            Requests to public sites (and to an .onion mempool server) go through it, e.g. a Tor
            proxy (socks5h://…:9050) so the sites don&apos;t see your IP address. Leave blank to
            connect directly.
          </p>
        </div>
        <input
          id="net-proxy-url"
          className="input"
          type="text"
          placeholder="socks5h://127.0.0.1:9050"
          value={proxyUrl}
          disabled={managed}
          onChange={(e) => setProxyUrl(e.target.value)}
        />
      </div>
      {!managed && (
        <div className="credential-submit-container">
          <button
            className="btn btn-primary"
            onClick={save}
            disabled={saving || !changed}
            aria-label="Save privacy & network settings"
          >
            {saving ? "Saving..." : "Save"}
          </button>
        </div>
      )}
    </div>
  );
};

export default NetworkSettings;
