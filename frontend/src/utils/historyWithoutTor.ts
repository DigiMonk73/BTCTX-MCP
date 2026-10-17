/**
 * The price card's one question about Tor (#241, the owner's option 1):
 * through Tor, Bitstamp refuses BitcoinTX's requests, so the card asks once
 * whether to download the price history without Tor. Yes lets only
 * Bitstamp's fixed history blocks go directly (backend/services/outbound.py,
 * history_client); No keeps everything on Tor. The answer is recorded and
 * changeable in Settings → Privacy & network.
 */

import type { NetworkSettingsData } from "./priceSource";
import type { PriceStatus, WithoutTorAnswer } from "./priceStatus";

export const QUESTION = "Download the price history once without Tor?";
export const QUESTION_WHY =
  "It's the same download for every install, and names none of your dates; Bitstamp would see this server's address.";
export const IF_YES =
  "Yes: only Bitstamp's price-history downloads go without Tor: the hourly history from 2013, the daily history, " +
  "and newer hours in the same fixed blocks when a value needs one. The live price and everything else stay on Tor.";
export const IF_NO = "No: nothing goes without Tor. Type older values, or use your own Mempool.";
export const CHANGE_LATER = "You can change this in Settings → Privacy & network.";
export const YES_LABEL = "Yes, download without Tor";
export const NO_LABEL = "No, keep everything on Tor";

export function answerOf(saved: NetworkSettingsData | null): WithoutTorAnswer {
  return saved?.history_without_tor?.answer ?? null;
}

/** The question is open: Bitstamp refused through Tor, nothing is answered, and prices may be asked. */
export function questionOpen(saved: NetworkSettingsData | null, status: PriceStatus | null): boolean {
  if (!saved || !status || !saved.proxy_url || answerOf(saved) !== null) return false;
  return status.bitstamp_refused === true && !status.invalid && !status.waiting;
}

/** The Dashboard card's first line: what Bitstamp's refusal keeps from downloading, as the history stands. */
export function refusedWords(status: PriceStatus): string {
  return status.history.shipped || status.history.state === "complete"
    ? "Through Tor, Bitstamp refuses BitcoinTX's requests, so newer hours and past days don't download."
    : "The hourly history didn't download: through Tor, Bitstamp refuses BitcoinTX's requests.";
}

/** "Yes, since Oct 16, 2026 (answered on the Dashboard)": the recorded answer, while Tor is on. */
export function answeredWords(saved: NetworkSettingsData): string | null {
  const record = saved.history_without_tor;
  if (!saved.proxy_url || !record?.answer) return null;
  const day = record.at
    ? new Date(record.at).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })
    : null;
  const where = record.via === "dashboard" ? "on the Dashboard" : "in Settings";
  const when = day ? `, since ${day} (answered ${where})` : "";
  return record.answer === "yes"
    ? `Bitstamp's price history without Tor: yes${when}. Only its fixed history blocks go without Tor; the live price and everything else stay on Tor.`
    : `Bitstamp's price history without Tor: no${when}. Everything stays on Tor, so the history doesn't download while Bitstamp refuses Tor.`;
}

/** The button that changes a recorded answer. */
export function changeLabel(answer: WithoutTorAnswer): string {
  return answer === "yes" ? "Keep it on Tor instead" : "Download it without Tor";
}
