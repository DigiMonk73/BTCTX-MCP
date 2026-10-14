import React from "react";
import { MEMPOOL_PLACEHOLDER, TOR_PLACEHOLDER, isOnion, torOffered, type PriceForm } from "../../utils/priceSource";
import { TOR_REFUSED } from "../../utils/priceStatus";

interface Props {
  form: PriceForm;
  set: (patch: Partial<PriceForm>) => void;
  /** A message under a field, e.g. the server's answer to a bad address. */
  errors: { mempoolUrl?: string; torUrl?: string };
  /** Tor is the server's (StartOS's action), locked on; or BitcoinTX runs on StartOS without it. */
  tor: { fromServer: boolean; onStartOS: boolean };
}

/** "Through Tor", and Tor's address once ticked. An .onion Mempool always
 * goes through Tor, so the box is ticked and fixed then. */
const TorField: React.FC<Props> = ({ form, set, errors, tor }) => {
  const onion = form.source === "mempool" && isOnion(form.mempoolUrl);
  const ticked = form.tor || onion;
  if (tor.fromServer) {
    return (
      <div className="price-field">
        <label className="price-tick">
          <input type="checkbox" checked disabled aria-describedby="price-tor-help" />
          <span>Through Tor</span>
        </label>
        <p id="price-tor-help" className="price-help">
          Tor on this server, set in StartOS: every request to a public site, and an .onion, goes through it. {TOR_REFUSED}
        </p>
      </div>
    );
  }
  return (
    <div className="price-field">
      <label className="price-tick">
        <input
          type="checkbox"
          checked={ticked}
          disabled={onion}
          onChange={(e) => set({ tor: e.target.checked })}
          aria-describedby="price-tor-help"
        />
        <span>Through Tor</span>
      </label>
      <p id="price-tor-help" className="price-help">
        {onion
          ? "An .onion address is reached through Tor."
          : tor.onStartOS
            ? "Turn on Use Tor in StartOS's Price Source & Privacy action, or type another proxy's address."
            : ticked
              ? `Hides your IP address too. Needs Tor running. ${TOR_REFUSED}`
              : "Hides your IP address too. Needs Tor running."}
      </p>
      {ticked && (
        <>
          <label className="price-field-label" htmlFor="price-tor-url">
            Tor&apos;s address
          </label>
          <input
            id="price-tor-url"
            className="input"
            type="text"
            placeholder={TOR_PLACEHOLDER}
            value={form.torUrl}
            aria-invalid={errors.torUrl ? true : undefined}
            aria-describedby={errors.torUrl ? "price-tor-url-help price-tor-url-error" : "price-tor-url-help"}
            onChange={(e) => set({ torUrl: e.target.value })}
          />
          <p id="price-tor-url-help" className="price-help">
            {tor.onStartOS ? "On StartOS, Use Tor in the action is simpler: it fills this in." : "Any proxy works."}
          </p>
          {errors.torUrl && (
            <p id="price-tor-url-error" className="field-error">
              {errors.torUrl}
            </p>
          )}
        </>
      )}
    </div>
  );
};

/** The fields that belong to the chosen choice, right after it. */
const ChoiceFields: React.FC<Props> = (props) => {
  const { form, set, errors } = props;
  if (form.source === "mempool") {
    return (
      <div className="price-fields">
        <div className="price-field">
          <label className="price-field-label" htmlFor="price-mempool-url">
            Your Mempool&apos;s address
          </label>
          <input
            id="price-mempool-url"
            className="input"
            type="url"
            placeholder={MEMPOOL_PLACEHOLDER}
            value={form.mempoolUrl}
            aria-invalid={errors.mempoolUrl ? true : undefined}
            aria-describedby={
              errors.mempoolUrl ? "price-mempool-url-help price-mempool-url-error" : "price-mempool-url-help"
            }
            onChange={(e) => set({ mempoolUrl: e.target.value })}
          />
          <p id="price-mempool-url-help" className="price-help">
            On your network, or an .onion (then through Tor).
          </p>
          {errors.mempoolUrl && (
            <p id="price-mempool-url-error" className="field-error">
              {errors.mempoolUrl}
            </p>
          )}
        </div>
        <div className="price-field">
          <label className="price-tick">
            <input
              type="checkbox"
              checked={form.backup}
              onChange={(e) => set({ backup: e.target.checked })}
              aria-describedby="price-backup-help"
            />
            <span>If it can&apos;t answer, ask public price sites</span>
          </label>
          <p id="price-backup-help" className="price-help">
            Bitstamp and Kraken. They see your IP address and when BitcoinTX is open, never your dates.
          </p>
        </div>
        {torOffered(form) && <TorField {...props} />}
      </div>
    );
  }
  if (form.source === "public") {
    return (
      <div className="price-fields">
        <TorField {...props} />
      </div>
    );
  }
  return null;
};

export default ChoiceFields;
