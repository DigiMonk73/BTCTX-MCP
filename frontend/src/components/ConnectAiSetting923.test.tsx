// @vitest-environment jsdom
// Settings › Connect an AI Assistant: the setup prompt asks the AI to have AI
// access turned on only while it's off, following the switch (#923).
import "../test/setup";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it } from "vitest";
import api from "../api";
import { ToastProvider } from "../contexts/ToastContext";
import { answers } from "../test/endedSession";
import ConnectAiSetting from "./ConnectAiSetting";

const instanceAdapter = api.defaults.adapter;
const ASKS = "AI access is off until I turn it on";

afterEach(() => {
  api.defaults.adapter = instanceAdapter;
});

/** A server whose AI access starts as `on`, and saves the switch. */
function serverWithAccess(on: boolean) {
  let access = { mode: "server", on, has_key: true, key_file: null };
  api.defaults.adapter = answers((config) => {
    if (config.url === "/health") return [200, { version: "2.0.1" }];
    if (config.method === "put") access = { ...access, ...JSON.parse(config.data) };
    return [200, access];
  });
}

function showSetup() {
  render(
    <ToastProvider>
      <ConnectAiSetting />
    </ToastProvider>,
  );
  return screen.getByLabelText<HTMLTextAreaElement>("Setup prompt");
}

it("doesn't ask for AI access once it's on", async () => {
  serverWithAccess(true);
  const prompt = showSetup();
  await screen.findByLabelText("Let AI assistants use BitcoinTX");
  expect(prompt.value).toContain("Once it's connected, call get_portfolio");
  expect(prompt.value).not.toContain(ASKS);
});

it("asks for it while it's off, and stops once it's turned on", async () => {
  serverWithAccess(false);
  const prompt = showSetup();
  const toggle = await screen.findByLabelText("Let AI assistants use BitcoinTX");
  expect(prompt.value).toContain(ASKS);
  await userEvent.setup().click(toggle);
  await waitFor(() => expect(prompt.value).not.toContain(ASKS));
});
