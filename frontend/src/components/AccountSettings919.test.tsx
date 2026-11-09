// @vitest-environment jsdom
// Settings' Reset Username & Password on a page whose session ended (another
// browser changed the password: SECURITY-RULES.md, "Sessions"): it goes to
// the sign-in page, and never says "No user found to reset credentials.",
// when the user is there and only the session ended (#919).
import "../test/setup";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import api from "../api";
import { ToastProvider } from "../contexts/ToastContext";
import { NOT_AUTHENTICATED, answers, pageAt } from "../test/endedSession";
import AccountSettings from "./AccountSettings";

const instanceAdapter = api.defaults.adapter;

afterEach(() => {
  api.defaults.adapter = instanceAdapter;
  vi.unstubAllGlobals();
});

it.fails("goes to the sign-in page, never saying no user was found", async () => {
  const sentTo = pageAt("/settings");
  // The section loads while the session is open; it ends before Update
  let ended = false;
  api.defaults.adapter = answers((config) => {
    if (ended) return NOT_AUTHENTICATED;
    if (config.url === "/users/setup-status") return [200, { has_user: true, is_default: false, setup_code_required: false }];
    return [200, { timezone: "UTC", source: "setting" }];
  });
  vi.spyOn(window, "confirm").mockReturnValue(true);
  const setMessage = vi.fn();
  render(
    <ToastProvider>
      <AccountSettings loading={false} setLoading={vi.fn()} setMessage={setMessage} />
    </ToastProvider>,
  );
  await screen.findByText("UTC", { selector: "strong" });
  expect(sentTo).toEqual([]);

  ended = true;
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("New password"), "a-new-password-1234");
  await user.type(screen.getByLabelText("Current password"), "the-current-password");
  await user.click(screen.getByRole("button", { name: "Update" }));
  await waitFor(() => expect(sentTo).toEqual(["/login"]));
  expect(setMessage).not.toHaveBeenCalledWith("No user found to reset credentials.");
});
