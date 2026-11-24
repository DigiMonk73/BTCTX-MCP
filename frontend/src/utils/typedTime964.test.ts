// #964: a typed time goes to the server with its text and the device's
// zone, for the server to read by its own timezone rules; a time the form
// put in itself goes as the moment it was, so an out-of-date device can't
// move it by reading its own (wrong) display again.
import { describe, expect, it } from "vitest";
import { deviceRulesWarning } from "../components/transactionForm/saveTransaction";
import { deviceZone, mapTransactionToFormData, shownTime, timePayload } from "./transactionForm";

describe("timePayload", () => {
  const shown = { iso: "2026-11-15T21:00:00.000Z", local: "2026-11-15T13:00:00" };

  it("sends a time the form put in itself, left alone, as the moment it was", () => {
    expect(timePayload({ timestamp: shown.local, timestampShown: shown })).toEqual({ timestamp: shown.iso });
  });

  it("sends a typed time with its text and the device's zone", () => {
    const sent = timePayload({ timestamp: "2026-11-15T14:00", timestampShown: shown });
    expect(sent.typed_time).toEqual({ local: "2026-11-15T14:00", zone: deviceZone() });
    expect(sent.timestamp).toBe(new Date("2026-11-15T14:00").toISOString());  // the device's reading, beside it
  });

  it("treats a form with no shown time as typed", () => {
    expect(timePayload({ timestamp: "2026-11-15T14:00" }).typed_time?.local).toBe("2026-11-15T14:00");
  });

  it("knows this device's zone", () => {
    expect(deviceZone()).toBeTruthy();
  });
});

describe("a saved row's Date & Time", () => {
  it("is shown, and remembered, as the moment saved", () => {
    const shownNow = shownTime(new Date("2026-11-15T21:00:00Z"));
    expect(shownNow.iso).toBe("2026-11-15T21:00:00.000Z");
    expect(new Date(shownNow.local).toISOString()).toBe(shownNow.iso);
  });

  it("comes back unchanged when the edit leaves it alone", () => {
    const tx = { id: 1, type: "Deposit", timestamp: "2026-11-15T21:00:00Z", from_account_id: 99, to_account_id: 1,
      amount: 100, fee_amount: 0, fee_currency: "USD", source: "N/A" } as unknown as ITransaction;
    const data = mapTransactionToFormData(tx);
    expect(timePayload(data)).toEqual({ timestamp: "2026-11-15T21:00:00.000Z" });
  });
});

describe("deviceRulesWarning", () => {
  const typed = { timestamp: "2026-11-15T22:00:00.000Z", typed_time: { local: "2026-11-15T14:00", zone: "America/Vancouver" } };

  it("says nothing when nothing was typed, or the server read it as this device did", () => {
    expect(deviceRulesWarning({ timestamp: typed.timestamp } as ICreateTransactionPayload, "2026-11-15T21:00:00Z"))
      .toBeUndefined();
    expect(deviceRulesWarning(typed as ICreateTransactionPayload, "2026-11-15T22:00:00Z")).toBeUndefined();
  });

  it("says the typed time is saved, and how far off this device shows it", () => {
    expect(deviceRulesWarning(typed as ICreateTransactionPayload, "2026-11-15T21:00:00Z")).toBe(
      "Saved at the time you typed. This device's timezone rules are out of date, so it shows this " +
      "transaction's time an hour off until its system or browser is updated.");
    expect(deviceRulesWarning(typed as ICreateTransactionPayload, "2026-11-15T21:30:00Z")).toContain("30 minutes off");
    expect(deviceRulesWarning(typed as ICreateTransactionPayload, "2026-11-15T20:00:00Z")).toContain("2 hours off");
  });
});
