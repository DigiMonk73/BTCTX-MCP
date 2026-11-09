// @vitest-environment jsdom
// A restore signs the restoring browser out (routers/backup.py) and, with a
// notice, waits on Settings for the owner to read it (#407). Meanwhile a 401
// (the price card asks every 30 s) leaves the page where it is; once the
// notice goes, or a restore failed, the next 401 goes to the sign-in page
// as any other ended session's does (#919): a hold that stuck would leave a
// signed-out browser on a page of errors.
import "../test/setup";
import React, { useState } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import api from "../api";
import { NOT_AUTHENTICATED, answers, pageAt } from "../test/endedSession";
import BackupRestore from "./BackupRestore";

const instanceAdapter = api.defaults.adapter;

afterEach(() => {
  api.defaults.adapter = instanceAdapter;
  vi.unstubAllGlobals();
});

const NOTICE = "The backup's AI access was off: turn it on again in Settings if you use it.";

/** The restore answered with `restore` (a status and its body); every
 * request after it 401, its session ended (a restore signs this browser
 * out; after one that failed, another browser's password change). */
function serverRestoring(restore: [number, unknown]) {
  let answered = false;
  api.defaults.adapter = answers(() => {
    if (answered) return NOT_AUTHENTICATED;
    answered = true;
    return restore;
  });
}

/** Settings' Backup & Restore and its message line, in React's strict mode
 * (each effect run twice), as the app runs it. */
function Settings() {
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  return (
    <>
      <BackupRestore loading={loading} setLoading={setLoading} setMessage={setMessage} />
      {message && <p role="status">{message}</p>}
    </>
  );
}

/** A form's data with the backup file in it. jsdom leaves a file chosen in a
 * test out of a form's data (and finds the required field empty), so the
 * restore's form gets it here, as a browser's would. */
class WithBackupFile extends FormData {
  constructor(form?: HTMLFormElement) {
    super(form);
    if (form?.querySelector('input[type="file"]')) this.set("file", new File(["backup"], "ledger.btx"));
  }
}

/** A backup restored through the form; its answer's message is on the page. */
async function restore() {
  vi.stubGlobal("FormData", WithBackupFile);
  const view = render(<React.StrictMode><Settings /></React.StrictMode>);
  await userEvent.setup().type(screen.getByLabelText("Backup password"), "the-backup-password");
  fireEvent.submit(screen.getByRole("button", { name: "Restore" }).closest("form")!);
  await screen.findByRole("status");
  return view;
}

/** The price card's question every 30 s (usePriceCard.ts). */
const pricePoll = () => expect(api.get("/bitcoin/price/status")).rejects.toMatchObject({ response: { status: 401 } });

describe("a restore's notice", () => {
  it("keeps the page on Settings with it while it shows", async () => {
    const sentTo = pageAt("/settings");
    serverRestoring([200, { message: "Backup restored.", notice: NOTICE }]);
    await restore();
    await pricePoll();
    expect(sentTo).toEqual([]);
    expect(screen.getByRole("status").textContent).toContain(NOTICE);
    expect(screen.getByRole("button", { name: "Log in again" })).toBeTruthy();
  });

  it("holds nothing once it's gone: the next 401 goes to the sign-in page", async () => {
    const sentTo = pageAt("/settings");
    serverRestoring([200, { message: "Backup restored.", notice: NOTICE }]);
    const view = await restore();
    view.unmount(); // the owner left Settings
    await pricePoll();
    expect(sentTo).toEqual(["/login"]);
  });

  it("ends at the owner's next action with Settings' message line: its 401 goes to the sign-in page", async () => {
    // Every such action (Recalculate, Export CSV…) starts by clearing the
    // line, the notice with it, and shares the sections' `loading`
    const sentTo = pageAt("/settings");
    serverRestoring([200, { message: "Backup restored.", notice: NOTICE }]);
    await restore();
    await userEvent.setup().click(screen.getByRole("button", { name: "Export CSV" }));
    await waitFor(() => expect(sentTo).toEqual(["/login"]));
  });

  it("holds nothing after a restore that failed", async () => {
    const sentTo = pageAt("/settings");
    serverRestoring([400, { detail: "Wrong password, or not a BitcoinTX backup." }]);
    await restore();
    expect(screen.getByRole("status").textContent).toContain("Wrong password");
    await pricePoll();
    expect(sentTo).toEqual(["/login"]);
  });
});
