// Settings section: AI access and the AI key, a prompt to hand to an AI app
// (Claude, Grok Build, any MCP client) so it installs the BitcoinTX MCP server
// on this computer, and the configurations for doing it by hand. See
// utils/aiSetup.ts.

import React, { useEffect, useMemo, useState } from "react";
import api from "../api";
import { useToast } from "../contexts/useToast";
import {
  KEY_PLACEHOLDER,
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
      <textarea className="input ai-copy-text" readOnly value={text} rows={rows} aria-label={label} />
      <button type="button" className="btn btn-primary" onClick={copy}>
        Copy
      </button>
    </div>
  );
};

interface AiAccess {
  /** "mac": the key is in the app's private key file; "server": created here. */
  mode: "mac" | "server";
  on: boolean;
  has_key: boolean;
  key_file: string | null;
}

/**
 * AI access on every edition: the switch, and the key. The Mac app keeps its
 * key in a file (Reset key); Docker and StartOS create, replace and revoke it
 * here, and show a new key once.
 */
const AiAccessControls: React.FC<{ access: AiAccess; onChange: (a: AiAccess) => void }> = ({
  access,
  onChange,
}) => {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [newKey, setNewKey] = useState<string | null>(null);
  const mac = access.mode === "mac";

  const toggle = async (on: boolean) => {
    setBusy(true);
    onChange({ ...access, on }); // show the choice now; undone if saving fails
    try {
      const res = await api.put<AiAccess>("/settings/ai-access", { on });
      onChange(res.data);
      toast.success(on ? "AI assistants can use BitcoinTX." : "AI access is off.");
    } catch {
      onChange(access);
      toast.error("Couldn't change AI access.");
    } finally {
      setBusy(false);
    }
  };

  const run = async (question: string | null, action: () => Promise<void>, failed: string) => {
    if (question && !window.confirm(question)) return;
    setBusy(true);
    try {
      await action();
    } catch {
      toast.error(failed);
    } finally {
      setBusy(false);
    }
  };

  const resetFile = () =>
    run(
      "Reset the AI key? Copies of the old key stop working. Your AI app keeps working (it reads the new key).",
      async () => {
        onChange((await api.post<AiAccess>("/settings/ai-access/reset-key")).data);
        toast.success("AI key reset.");
      },
      "Couldn't reset the AI key."
    );

  const create = () =>
    run(
      access.has_key ? "Make a new AI key? Your AI app stops working until you paste the new key into it." : null,
      async () => {
        const { key, ...state } = (await api.post<AiAccess & { key: string }>("/settings/ai-key")).data;
        onChange(state);
        setNewKey(key);
      },
      "Couldn't create an AI key."
    );

  const revoke = () =>
    run(
      "Revoke the AI key? Your AI app can't use BitcoinTX until you create a new key.",
      async () => {
        onChange((await api.delete<AiAccess>("/settings/ai-key")).data);
        setNewKey(null);
        toast.success("AI key revoked.");
      },
      "Couldn't revoke the AI key."
    );

  return (
    <div className="settings-option">
      <div className="option-info">
        <span className="settings-option-title">AI access</span>
        <p className="settings-option-subtitle">
          {mac ? (
            <>
              AI apps on this Mac reach BitcoinTX with a key the app keeps in a private file
              {access.key_file ? <> (<code>{access.key_file}</code>)</> : null}, never your password.
              Reset it if that file may have been copied.
            </>
          ) : (
            <>
              AI apps reach BitcoinTX with an AI key you create here and paste into the AI
              app&apos;s settings, never your password. The key can read your ledger, add or change
              entries and make a backup; it can&apos;t log in, change your password, restore or
              delete everything. Revoke it here at any time.
            </>
          )}
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
        <p className="settings-option-subtitle">
          When on, an AI app with the key can read your ledger and add, edit or delete
          transactions. BitcoinTX itself sends your ledger nowhere, but what the AI reads goes to
          wherever its model runs (see above). Off: nothing can use the key.
        </p>
        {newKey && (
          <div className="ai-new-key" role="group" aria-label="New AI key">
            <p className="note note-warning">
              This is the only time BitcoinTX shows this key. Paste it into your AI app&apos;s
              settings now.{!access.on && " Then turn on AI access above: the key works only while it's on."}
            </p>
            <CopyBlock label="AI key" text={newKey} rows={2} />
          </div>
        )}
      </div>
      <div className="ai-key-actions">
        {mac ? (
          <button type="button" className="btn btn-secondary" onClick={resetFile} disabled={busy}>
            Reset key
          </button>
        ) : access.has_key ? (
          <>
            <button type="button" className="btn btn-secondary" onClick={create} disabled={busy}>
              New key
            </button>
            <button type="button" className="btn btn-danger" onClick={revoke} disabled={busy}>
              Revoke
            </button>
          </>
        ) : (
          <button type="button" className="btn btn-primary" onClick={create} disabled={busy}>
            Create AI key
          </button>
        )}
      </div>
    </div>
  );
};

const ConnectAiSetting: React.FC = () => {
  const [version, setVersion] = useState<string | undefined>();
  const [access, setAccess] = useState<AiAccess | null>(null);
  const url = window.location.origin;

  useEffect(() => {
    api
      .get<{ version?: string }>("/health")
      .then((res) => setVersion(res.data.version))
      .catch(() => undefined);
    api
      .get<AiAccess>("/settings/ai-access")
      .then((res) => setAccess(res.data))
      .catch(() => undefined);
  }, []);

  const keyMode = access?.mode === "mac";
  const input = useMemo(() => ({ url, version, keyMode }), [url, version, keyMode]);

  return (
    <div className="settings-section" role="region" aria-label="Connect an AI Assistant">
      <h3 className="section-title">Connect an AI Assistant</h3>
      <p className="note note-warning ai-privacy-note" role="note">
        <strong>Your data goes to the AI&apos;s model.</strong> Whatever BitcoinTX hands the
        assistant (transactions, balances, gains) and whatever you paste into the chat is read by
        its model. With a cloud AI such as Claude or Grok, that means the provider&apos;s
        servers. To keep it on your computer, use an app that runs a local model, such as LM
        Studio or Goose with Ollama.{" "}
        <a
          href="https://github.com/DigiMonk73/BTCTX-MCP/blob/main/mcp_server/README.md#privacy-cloud-or-local-model"
          target="_blank"
          rel="noreferrer"
        >
          More
        </a>
      </p>
      {access && <AiAccessControls access={access} onChange={setAccess} />}
      <div className="settings-option ai-setup">
        <div className="option-info">
          <span className="settings-option-title">Setup prompt</span>
          <p className="settings-option-subtitle">
            Paste this into an AI app on this computer that can use MCP servers (Claude
            Desktop, Claude Code, Grok Build, LM Studio…). It sets up the BitcoinTX MCP server
            here, so the AI can read your ledger and enter transactions (its guide tells it to
            show you a preview before saving).
            {keyMode
              ? " No key or address is needed: the MCP server finds this app by itself. Keep BitcoinTX open while you use the AI."
              : " Your AI key stays out of the chat: you paste it into the AI app's settings yourself."}
            {access && !access.on && " Turn on AI access above first."}
          </p>
          <CopyBlock label="Setup prompt" text={buildAiPrompt(input)} rows={keyMode ? 12 : 18} />

          <details className="ai-setup-manual">
            <summary>Set it up yourself</summary>
            <p className="settings-option-subtitle">
              {!keyMode && (
                <>
                  Replace <code>{KEY_PLACEHOLDER}</code> with the AI key you created above.{" "}
                </>
              )}
              Needs <a href="https://docs.astral.sh/uv/" target="_blank" rel="noreferrer">uv</a>{" "}
              (<code>brew install uv</code> on a Mac).
              {needsCaBundle(url) &&
                " Save this server's root CA certificate as a file and put its path in BTCTX_CA_BUNDLE (on StartOS, the Connect an AI Assistant action has it)."}
            </p>
            <span className="settings-option-title ai-setup-heading">Claude Desktop or LM Studio</span>
            <p className="settings-option-subtitle">
              Claude Desktop: Settings → Developer → Edit Config. LM Studio: Program tab → Install →
              Edit <code>mcp.json</code>. Merge this in, then restart the app. If it can&apos;t find{" "}
              <code>uvx</code>, use the full path from <code>which uvx</code>.
            </p>
            <CopyBlock label="Claude Desktop config" text={claudeDesktopConfig(input)} rows={keyMode ? 12 : 15} />
            <span className="settings-option-title ai-setup-heading">Claude Code</span>
            <p className="settings-option-subtitle">
              Run in a terminal.
              {!keyMode && " Your shell keeps commands in its history, key included; the file above avoids that."}
            </p>
            <CopyBlock label="Claude Code command" text={claudeCodeCommand(input)} rows={keyMode ? 3 : 5} />
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
