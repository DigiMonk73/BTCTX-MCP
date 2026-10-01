import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import "../styles/transactionPanel.css";
import TransactionForm from "./TransactionForm";

interface TransactionPanelProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmitSuccess?: () => void;
  transactionId?: number | null; // For editing
}

const TransactionPanel: React.FC<TransactionPanelProps> = ({
  isOpen,
  onClose,
  onSubmitSuccess,
  transactionId,
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

  // A click outside, Escape or the close button: close, or ask first when
  // there are unsaved changes
  const requestClose = useCallback(() => {
    if (isFormDirty) {
      setShowDiscardModal(true);
    } else {
      onClose();
    }
  }, [isFormDirty, onClose]);

  // What Escape does now, read when the key is pressed. With "Discard
  // changes?" showing, it is that question's safe answer: Go back.
  const onEscape = useRef(requestClose);
  useLayoutEffect(() => {
    onEscape.current = showDiscardModal ? () => setShowDiscardModal(false) : requestClose;
  }, [showDiscardModal, requestClose]);

  useEffect(() => {
    if (!isOpen) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !e.defaultPrevented) onEscape.current();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [isOpen]);

  const handleDiscardChanges = () => {
    setShowDiscardModal(false);
    onClose();
  };

  const handleGoBack = () => {
    setShowDiscardModal(false);
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
      <div className="transaction-panel">
        <div className="panel-header">
          <h2>{transactionId ? "Edit Transaction" : "Add Transaction"}</h2>
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

      {showDiscardModal && (
        <div className="discard-modal">
          <div className="discard-modal-content card" role="dialog" aria-modal="true">
            <h3 className="card-title">Discard changes?</h3>
            <p>Your changes have not been saved. If you close this panel, they will be lost.</p>
            <div className="discard-modal-actions">
              <button type="button" onClick={handleGoBack} className="btn btn-secondary">Go back</button>
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
