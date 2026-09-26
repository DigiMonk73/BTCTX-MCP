import React, { useEffect, useState } from "react";
import axios from "axios";
import api from "../api";
import { useToast } from "../contexts/useToast";

interface NetworkSettingsData {
  live_data: boolean;
  mempool_url: string | null;
  proxy_url: string | null;
}

/**
 * Settings → Privacy & network (backend/services/outbound.py). Public price
 * and block-height services stay the default; the owner can turn live data
 * off, use their own mempool server, and send every outside request through
 * a proxy such as Tor.
 */
const NetworkSettings: React.FC = () => {
  const toast = useToast();
  const [saved, setSaved] = useState<NetworkSettingsData | null>(null);
  const [liveData, setLiveData] = useState(true);
  const [mempoolUrl, setMempoolUrl] = useState("");
  const [proxyUrl, setProxyUrl] = useState("");
  const [saving, setSaving] = useState(false);

  const show = (data: NetworkSettingsData) => {
    setSaved(data);
    setLiveData(data.live_data);
    setMempoolUrl(data.mempool_url ?? "");
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
    (liveData !== saved.live_data ||
      mempoolUrl.trim() !== (saved.mempool_url ?? "") ||
      proxyUrl.trim() !== (saved.proxy_url ?? ""));

  const save = async () => {
    setSaving(true);
    try {
      const res = await api.put<NetworkSettingsData>("/settings/network", {
        live_data: liveData,
        mempool_url: mempoolUrl.trim() || null,
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

  return (
    <div className="settings-section" role="region" aria-label="Privacy & network">
      <h3 className="section-title">Privacy &amp; Network</h3>
      <div className="settings-option">
        <div className="option-info">
          <label className="settings-option-title" htmlFor="net-live-data">
            Live data
          </label>
          <p className="settings-option-subtitle">
            On: the BTC price and block height come from public services (CoinGecko, Kraken,
            Blockchain.info, mempool.space…), and past prices BitcoinTX doesn't have yet are
            downloaded. Off: no public service is asked; past prices come only from those already
            stored, and your own mempool server below is still used.
          </p>
        </div>
        <input
          id="net-live-data"
          type="checkbox"
          checked={liveData}
          onChange={(e) => setLiveData(e.target.checked)}
        />
      </div>
      <div className="settings-option stacked">
        <div className="option-info">
          <label className="settings-option-title" htmlFor="net-mempool-url">
            Your own mempool server
          </label>
          <p className="settings-option-subtitle">
            Asked first for the live price and block height, e.g. http://umbrel.local:3006 or an
            .onion address. Leave blank to use only public services.
          </p>
        </div>
        <input
          id="net-mempool-url"
          className="input"
          type="url"
          placeholder="http://umbrel.local:3006"
          value={mempoolUrl}
          onChange={(e) => setMempoolUrl(e.target.value)}
        />
      </div>
      <div className="settings-option stacked">
        <div className="option-info">
          <label className="settings-option-title" htmlFor="net-proxy-url">
            Proxy for outside requests
          </label>
          <p className="settings-option-subtitle">
            Every outside request goes through it, e.g. socks5h://127.0.0.1:9050 for Tor. Leave
            blank to connect directly.
          </p>
        </div>
        <input
          id="net-proxy-url"
          className="input"
          type="text"
          placeholder="socks5h://127.0.0.1:9050"
          value={proxyUrl}
          onChange={(e) => setProxyUrl(e.target.value)}
        />
      </div>
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
    </div>
  );
};

export default NetworkSettings;
