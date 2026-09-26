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
  grokCommand,
  needsCaBundle,
} from "../utils/aiSetup";

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

interface AiAccess {
  /** True in the Mac app: the MCP server uses a key file, no password. */
  available: boolean;
  on: boolean;
  key_file: string | null;
}

/** Mac app: turn AI access on or off, and reset the key. */
const AiAccessControls: React.FC<{ access: AiAccess; onChange: (a: AiAccess) => void }> = ({
  access,
  onChange,
}) => {
  const toast = useToast();
  const [busy, setBusy] = useState(false);

  const toggle = async (on: boolean) => {
    setBusy(true);
    onChange({ ...access, on }); // show the choice now; undone if saving fails
    try {
      const res = await api.put<AiAccess>("/settings/ai-access", { on });
      onChange(res.data);
      toast.success(on ? "AI assistants can use BitcoinTX." : "AI assistant access is off.");
    } catch {
      onChange(access);
      toast.error("Couldn't change AI assistant access.");
    } finally {
      setBusy(false);
    }
  };

  const reset = async () => {
    if (!window.confirm("Reset the AI assistant key? Copies of the old key stop working. Your AI app keeps working (it reads the new key).")) {
      return;
    }
    setBusy(true);
    try {
      const res = await api.post<AiAccess>("/settings/ai-access/reset-key");
      onChange(res.data);
      toast.success("AI assistant key reset.");
    } catch {
      toast.error("Couldn't reset the AI assistant key.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="settings-option">
      <div className="option-info">
        <span className="settings-option-title">AI assistant access</span>
        <p className="settings-option-subtitle">
          AI apps on this Mac reach BitcoinTX with a key the app keeps in a private file
          {access.key_file ? <> (<code>{access.key_file}</code>)</> : null}, never your password.
          Reset it if that file may have been copied.
        </p>
        <label className="ai-access-toggle">
          <input
            type="checkbox"
            checked={access.on}
            disabled={busy}
            onChange={(e) => toggle(e.target.checked)}
          />{" "}
          Let AI assistants use BitcoinTX
        </label>
      </div>
      <button type="button" className="settings-button" onClick={reset} disabled={busy}>
        Reset key
      </button>
    </div>
  );
};

const ConnectAiSetting: React.FC = () => {
  const [username, setUsername] = useState("");
  const [version, setVersion] = useState<string | undefined>();
  const [access, setAccess] = useState<AiAccess | null>(null);
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
    api
      .get<AiAccess>("/settings/ai-access")
      .then((res) => setAccess(res.data))
      .catch(() => undefined);
  }, []);

  const keyMode = !!access?.available;
  const input = useMemo(
    () => ({ url, username: username || "YOUR_BITCOINTX_USERNAME", version, keyMode }),
    [url, username, version, keyMode]
  );

  return (
    <div className="settings-section" role="region" aria-label="Connect an AI Assistant">
      <h3>Connect an AI Assistant</h3>
      {access?.available && <AiAccessControls access={access} onChange={setAccess} />}
      <div className="settings-option ai-setup">
        <div className="option-info">
          <span className="settings-option-title">Setup prompt</span>
          <p className="settings-option-subtitle">
            Paste this into Claude, Grok Build or another AI app that can use MCP servers. It
            sets up the BitcoinTX MCP server on your computer, so the AI can read your ledger
            and enter transactions (it shows you a preview first).
            {keyMode
              ? " No password or address is needed: the MCP server finds this app by itself. Keep BitcoinTX open while you use the AI."
              : " Your password stays out of the chat: you type it into the configuration yourself."}
          </p>
          <CopyBlock label="Setup prompt" text={buildAiPrompt(input)} rows={keyMode ? 12 : 19} />

          <details className="ai-setup-manual">
            <summary>Set it up yourself</summary>
            <p className="settings-option-subtitle">
              {!keyMode && (
                <>
                  Replace <code>{PASSWORD_PLACEHOLDER}</code> with your BitcoinTX password.{" "}
                </>
              )}
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
            <CopyBlock label="Claude Desktop config" text={claudeDesktopConfig(input)} rows={keyMode ? 12 : 19} />
            <span className="settings-option-title ai-setup-heading">Claude Code</span>
            <p className="settings-option-subtitle">Run in a terminal.</p>
            <CopyBlock label="Claude Code command" text={claudeCodeCommand(input)} rows={keyMode ? 3 : 6} />
            {keyMode && (
              <>
                <span className="settings-option-title ai-setup-heading">Grok Build</span>
                <p className="settings-option-subtitle">Run in a terminal.</p>
                <CopyBlock label="Grok Build command" text={grokCommand(input)} rows={2} />
              </>
            )}
          </details>
        </div>
      </div>
    </div>
  );
};

export default ConnectAiSetting;
