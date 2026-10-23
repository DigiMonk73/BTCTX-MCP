// Settings' tax timezone Save says the server's reason when it isn't saved
// (#533): it said "Could not save the timezone." whatever went wrong, where
// the rest of Settings shows the server's words (detailOr).
import { AxiosError, AxiosHeaders, type AxiosResponse } from "axios";
import { describe, expect, it } from "vitest";
import { timezoneNotSaved } from "./taxTimezone";

function apiError(status: number, data: unknown): AxiosError {
  const config = { headers: new AxiosHeaders() };
  const response = { status, statusText: "", data, headers: {}, config } as AxiosResponse;
  return new AxiosError("Request failed with status code " + status, "ERR_BAD_REQUEST", config, null, response);
}

describe("timezoneNotSaved (#533)", () => {
  it("says the server's reason", () => {
    // A zone the browser lists that the server's tzdata doesn't have (#407)
    const unknown = "Unknown timezone 'America/Ciudad_Juarez'. Use an IANA name like America/Chicago.";
    expect(timezoneNotSaved(apiError(400, { detail: unknown }))).toBe(unknown);
    const busy = "BitcoinTX was busy saving something else, and nothing was changed. Try again.";
    expect(timezoneNotSaved(apiError(503, { detail: busy }))).toBe(busy);
  });

  it("says its own sentence when the server gave no reason", () => {
    expect(timezoneNotSaved(apiError(502, "<html>Bad gateway</html>"))).toBe("Could not save the timezone.");
    expect(timezoneNotSaved(new Error("Network Error"))).toBe("Could not save the timezone.");
  });
});
