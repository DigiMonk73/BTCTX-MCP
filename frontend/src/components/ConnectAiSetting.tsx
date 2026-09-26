// FILE: frontend/src/components/ConnectAiSetting.tsx
//
// Settings section: a prompt to hand to an AI app (Claude, Grok Build, any
// MCP client) so it installs the BitcoinTX MCP server on this computer, plus
// the configurations for doing it by hand. See utils/aiSetup.ts.

import React, { useEffect, useMemo, useState } from "react";
import api from "../api";
import { useToast } from "../contexts/useToast";
import {
  PASSWORD_PLACEHOLDER,
  buildAiPrompt,
  claudeCodeCommand,
  claudeDesktopConfig,
  needsCaBundle,
} from "../utils/aiSetup";
import { isDesktopApp } from "../utils/desktopDownload";

/** Clipboard API where allowed (https, localhost); else the older copy command. */
async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // fall through
  }
  const area = document.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "");
  area.style.position = "fixed";
  area.style.opacity = "0";
  document.body.appendChild(area);
  area.select();
  try {
    return document.execCommand("copy");
  } catch {
    return false;
  } finally {
    document.body.removeChild(area);
  }
}

const CopyBlock: React.FC<{ label: string; text: string; rows: number }> = ({ label, text, rows }) => {
  const toast = useToast();
  const copy = async () => {
    if (await copyText(text)) toast.success(`${label} copied.`);
    else toast.error("Couldn't copy. Select the text and copy it yourself.");
  };
  return (
    <div className="ai-copy-block">
      <textarea className="ai-copy-text" readOnly value={text} rows={rows} aria-label={label} />
      <button type="button" className="settings-button" onClick={copy}>
        Copy
      </button>
    </div>
  );
};

const ConnectAiSetting: React.FC = () => {
  const [username, setUsername] = useState("");
  const [version, setVersion] = useState<string | undefined>();
  const url = window.location.origin;

  useEffect(() => {
    api
      .get<{ username: string }[]>("/users/")
      .then((res) => setUsername(res.data[0]?.username ?? ""))
      .catch(() => undefined);
    api
      .get<{ version?: string }>("/health")
      .then((res) => setVersion(res.data.version))
      .catch(() => undefined);
  }, []);

  const input = useMemo(
    () => ({ url, username: username || "YOUR_BITCOINTX_USERNAME", version }),
    [url, username, version]
  );

  return (
    <div className="settings-section" role="region" aria-label="Connect an AI Assistant">
      <h3>Connect an AI Assistant</h3>
      <div className="settings-option ai-setup">
        <div className="option-info">
          <span className="settings-option-title">Setup prompt</span>
          <p className="settings-option-subtitle">
            Paste this into Claude, Grok Build or another AI app that can use MCP servers. It
            sets up the BitcoinTX MCP server on your computer, so the AI can read your ledger
            and enter transactions (it shows you a preview first). Your password stays out of
            the chat: you type it into the configuration yourself.
            {isDesktopApp() && " Keep BitcoinTX open while you use the AI."}
          </p>
          <CopyBlock label="Setup prompt" text={buildAiPrompt(input)} rows={19} />

          <details className="ai-setup-manual">
            <summary>Set it up yourself</summary>
            <p className="settings-option-subtitle">
              Replace <code>{PASSWORD_PLACEHOLDER}</code> with your BitcoinTX password.
              Needs <a href="https://docs.astral.sh/uv/" target="_blank" rel="noreferrer">uv</a>{" "}
              (<code>brew install uv</code> on a Mac).
              {needsCaBundle(url) &&
                " Save this server's root CA certificate as a file and put its path in BTCTX_CA_BUNDLE (on StartOS, the Connect an AI Assistant action has it)."}
            </p>
            <span className="settings-option-title ai-setup-heading">Claude Desktop</span>
            <p className="settings-option-subtitle">
              Settings → Developer → Edit Config, merge this in, then restart Claude Desktop. If
              it can't find <code>uvx</code>, use the full path from <code>which uvx</code>.
            </p>
            <CopyBlock label="Claude Desktop config" text={claudeDesktopConfig(input)} rows={19} />
            <span className="settings-option-title ai-setup-heading">Claude Code</span>
            <p className="settings-option-subtitle">Run in a terminal.</p>
            <CopyBlock label="Claude Code command" text={claudeCodeCommand(input)} rows={6} />
          </details>
        </div>
      </div>
    </div>
  );
};

export default ConnectAiSetting;
