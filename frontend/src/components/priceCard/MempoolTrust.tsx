import React, { useState } from "react";
import axios from "axios";
import api from "../../api";
import { useToast } from "../../contexts/useToast";
import type { NetworkSettingsData } from "../../utils/priceSource";
import { mempoolProblem, type PriceStatus } from "../../utils/priceStatus";

const ROUTE = "/settings/network/mempool-certificate";

interface Offer {
  server: string;
  name: string;
  sha256: string;
}

interface Props {
  saved: NetworkSettingsData;
  status: PriceStatus | null;
  onChange: (settings: NetworkSettingsData) => void;
}

function why(err: unknown, fallback: string): string {
  const detail = axios.isAxiosError(err) ? err.response?.data?.detail : undefined;
  return typeof detail === "string" ? detail : fallback;
}

/**
 * A home server's own certificate for your Mempool (#188): offered when it's
 * why the Mempool can't be used and its address is a home-network one; the
 * owner sees the server, its root certificate's name and fingerprint first.
 * Once trusted, it can be forgotten here.
 */
const MempoolTrust: React.FC<Props> = ({ saved, status, onChange }) => {
  const toast = useToast();
  const [offer, setOffer] = useState<Offer | null>(null);
  const [busy, setBusy] = useState(false);
  if (saved.managed !== true && saved.price_source !== "mempool") return null;

  const run = async (work: () => Promise<void>, fallback: string) => {
    setBusy(true);
    try {
      await work();
    } catch (err) {
      toast.error(why(err, fallback));
    } finally {
      setBusy(false);
    }
  };
  const look = () => run(async () => setOffer((await api.get<Offer>(ROUTE)).data), "Could not reach your Mempool.");
  const trust = (sha256: string) =>
    run(async () => {
      onChange((await api.put<NetworkSettingsData>(ROUTE, { sha256 })).data);
      setOffer(null);
      toast.success("Trusted: BitcoinTX now uses your Mempool.");
    }, "Could not trust the certificate.");
  const forget = () =>
    run(async () => onChange((await api.delete<NetworkSettingsData>(ROUTE)).data), "Could not forget the certificate.");

  const trusted = saved.mempool_certificate;
  if (trusted) {
    return (
      <div className="price-trust">
        <p className="price-help">
          Trusted for your Mempool: {trusted.name} <span className="price-fingerprint">(SHA-256 {trusted.sha256})</span>
        </p>
        <button type="button" className="btn btn-secondary btn-sm" onClick={forget} disabled={busy}>
          Forget this server's certificate
        </button>
      </div>
    );
  }
  if (!saved.mempool_trustable || !status || mempoolProblem(status) !== "mempool_untrusted_certificate") return null;
  if (!offer) {
    return (
      <div className="price-trust">
        <button type="button" className="btn btn-secondary btn-sm" onClick={look} disabled={busy}>
          {busy ? "Looking…" : "Trust this server"}
        </button>
      </div>
    );
  }
  return (
    <div className="price-trust" role="group" aria-label="Trust this server">
      <p className="price-detail">
        {offer.server}'s certificate authority: <strong>{offer.name}</strong>
      </p>
      <p className="price-help price-fingerprint">SHA-256: {offer.sha256}</p>
      <p className="price-help">Only do this on your own home network.</p>
      <div className="price-actions">
        <button type="button" className="btn btn-primary btn-sm" onClick={() => trust(offer.sha256)} disabled={busy}>
          {busy ? "Trusting…" : "Trust"}
        </button>
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => setOffer(null)} disabled={busy}>
          Cancel
        </button>
      </div>
    </div>
  );
};

export default MempoolTrust;
