import React, { useCallback, useContext, useEffect, useLayoutEffect, useRef, useState } from "react";
import { useBlocker, type BlockerFunction } from "react-router-dom";
import { X } from "lucide-react";
import { ReportUnsavedChanges } from "../contexts/unsavedChanges";
import { keepFocusIn } from "../utils/dialogFocus";
import "../styles/transactionPanel.css";
import TransactionForm from "./TransactionForm";

interface TransactionPanelProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmitSuccess?: () => void;
  transactionId?: number | null; // For editing
  /** Focused as the panel closes when what opened it is gone (an edited row, reloaded by its save). */
  returnFocus?: React.RefObject<HTMLElement | null>;
}

const TransactionPanel: React.FC<TransactionPanelProps> = ({
  isOpen,
  onClose,
  onSubmitSuccess,
  transactionId,
  returnFocus,
}) => {
  const [showDiscardModal, setShowDiscardModal] = useState(false);
  const [isFormDirty, setIsFormDirty] = useState(false);
  const [isUpdating, setIsUpdating] = useState(false); // Tracks form submission status

  useEffect(() => {
    if (isOpen) {
      setShowDiscardModal(false);
      setIsFormDirty(false);
      setIsUpdating(false); 
    }
  }, [isOpen]);

  // A closed panel has nothing to lose, though isFormDirty keeps the last
  // form's answer (true after Discard changes) until the next opening
  const hasUnsavedChanges = isOpen && isFormDirty;

  // A click outside, Escape or the close button: close, or ask first when
  // there are unsaved changes
  const requestClose = useCallback(() => {
    if (isFormDirty) {
      setShowDiscardModal(true);
    } else {
      onClose();
    }
  }, [isFormDirty, onClose]);

  // Back, Forward or a page link to another page: the same question (#536).
  // A link to this page keeps the panel open, so it isn't asked then.
  const leavesWithChanges = useCallback<BlockerFunction>(
    ({ currentLocation, nextLocation }) =>
      hasUnsavedChanges && currentLocation.pathname !== nextLocation.pathname,
    [hasUnsavedChanges],
  );
  const leaving = useBlocker(leavesWithChanges);
  const askDiscard = showDiscardModal || leaving.state === "blocked";

  // While there are unsaved changes: a reload, closing the tab or Back out of
  // the app get the browser's question (only its own can stop those), and
  // the header's Logout leaves the asking to this panel
  const reportUnsaved = useContext(ReportUnsavedChanges);
  useEffect(() => {
    if (!hasUnsavedChanges) return;
    const askBrowser = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = true; // Chrome before 119 asks only when this is set
    };
    window.addEventListener("beforeunload", askBrowser);
    reportUnsaved(true);
    return () => {
      window.removeEventListener("beforeunload", askBrowser);
      reportUnsaved(false);
    };
  }, [hasUnsavedChanges, reportUnsaved]);

  // Go back: the panel stays as it is, and so does the page
  const keepEditing = useCallback(() => {
    setShowDiscardModal(false);
    leaving.reset?.();
  }, [leaving]);

  // What Escape does now, read when the key is pressed. With "Discard
  // changes?" showing, it is that question's safe answer: Go back.
  const onEscape = useRef(requestClose);
  useLayoutEffect(() => {
    onEscape.current = askDiscard ? keepEditing : requestClose;
  }, [askDiscard, keepEditing, requestClose]);

  // The panel is a modal dialog (#772): Tab stays in it, or in "Discard
  // changes?" over it. Another dialog over it (the past-year question) keeps
  // the keyboard in itself.
  const panel = useRef<HTMLDivElement>(null);
  const discard = useRef<HTMLDivElement>(null);
  const holdFocus = useRef<(e: KeyboardEvent) => void>(() => {});
  useLayoutEffect(() => {
    holdFocus.current = (e) => {
      if (askDiscard) keepFocusIn(discard.current, e);
      else if (!document.querySelector(".dialog-backdrop")) keepFocusIn(panel.current, e);
    };
  }, [askDiscard]);

  useEffect(() => {
    if (!isOpen) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !e.defaultPrevented) onEscape.current();
      holdFocus.current(e);
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [isOpen]);

  // Focus goes into the panel as it opens, and back to what opened it as it closes (a click in
  // Safari focuses no button, so the page itself had focus: then to `returnFocus`)
  useEffect(() => {
    if (!isOpen) return;
    const active = document.activeElement;
    const from = active instanceof HTMLElement && active !== document.body ? active : null;
    const fallback = returnFocus?.current;
    panel.current?.focus();
    return () => (from?.isConnected ? from : fallback)?.focus();
  }, [isOpen, returnFocus]);

  // "Discard changes?" takes the keyboard on its safe answer, and gives it back on Go back
  const goBack = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!askDiscard) return;
    const from = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    goBack.current?.focus();
    return () => from?.focus();
  }, [askDiscard]);

  // Discard changes: go where the user was going, or just close
  const handleDiscardChanges = () => {
    setShowDiscardModal(false);
    if (leaving.state === "blocked") {
      leaving.proceed();
    } else {
      onClose();
    }
  };

  const handleFormSubmitSuccess = () => {
    setIsUpdating(false);
    onClose();
    onSubmitSuccess?.();
  };

  const handleUpdateStatusChange = (updating: boolean) => {
    setIsUpdating(updating);
  };

  if (!isOpen) return null;

  return (
    <React.Fragment>
      <div className="transaction-panel-overlay" onClick={requestClose} />
      <div ref={panel} tabIndex={-1} className="transaction-panel" role="dialog" aria-modal="true"
        aria-labelledby="transaction-panel-title">
        <div className="panel-header">
          <h2 id="transaction-panel-title">{transactionId ? "Edit Transaction" : "Add Transaction"}</h2>
          {/* On a phone the panel covers the page: no outside to click, no
              Escape key, so this is the only way out without saving */}
          <button
            type="button"
            className="btn btn-quiet panel-close"
            onClick={requestClose}
            aria-label="Close"
            title="Close"
          >
            <X size={18} aria-hidden="true" />
          </button>
        </div>

        <div className="panel-body">
          <TransactionForm
            id="transaction-form"
            onDirtyChange={setIsFormDirty}
            onSubmitSuccess={handleFormSubmitSuccess}
            transactionId={transactionId}
            onUpdateStatusChange={handleUpdateStatusChange}
          />
        </div>

        <div className="panel-footer">
          <button
            className="btn btn-primary"
            type="submit"
            form="transaction-form"
            disabled={isUpdating}
          >
            {isUpdating
              ? "Saving..."
              : transactionId
              ? "Update transaction"
              : "Save transaction"}
          </button>
        
          {transactionId && (
            <button
              type="button"
              className="btn btn-danger"
              onClick={() => {
                // The form's delete handler asks "Are you sure?" (once) and deletes
                document.querySelector<HTMLButtonElement>("#trigger-form-delete")?.click();
              }}
              disabled={isUpdating}
            >
              Delete
            </button>
          )}
        </div>

      {askDiscard && (
        <div className="dialog-backdrop">
          <div ref={discard} className="dialog dialog-narrow card" role="dialog" aria-modal="true"
            aria-labelledby="discard-changes-title">
            <h3 id="discard-changes-title" className="card-title">Discard changes?</h3>
            <p>Your changes have not been saved. If you close this panel, they will be lost.</p>
            <div className="dialog-actions">
              <button ref={goBack} type="button" onClick={keepEditing} className="btn btn-secondary">Go back</button>
              <button type="button" onClick={handleDiscardChanges} className="btn btn-danger">
                Discard changes
              </button>
            </div>
          </div>
        </div>
      )}
      </div>
    </React.Fragment>
  );
};  

export default TransactionPanel;
