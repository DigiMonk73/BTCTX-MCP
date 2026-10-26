import React, { useState, useEffect, useLayoutEffect, useRef } from "react";
import { FormProvider, useForm, SubmitHandler } from "react-hook-form";
import api from "../api";
import { useToast } from "../contexts/useToast";
import "../styles/transactionForm.css";
import { serverReason } from "../utils/apiError";
import { parseTransaction } from "../utils/format";
import { mapTransactionToFormData, plainBtcText, toDatetimeLocal } from "../utils/transactionForm";
import { ACCOUNTS_FAILED, useAccounts } from "../utils/useAccounts";
import PastYearDialog from "./PastYearDialog";
import TypeFields from "./transactionForm/TypeFields";
import { deleteTransaction, saveFailedMessage, saveTransaction } from "./transactionForm/saveTransaction";
import { useFieldAutofill } from "./transactionForm/useFieldAutofill";
import { usePastYearWarning } from "./transactionForm/usePastYearWarning";

// What a change of type resets, and a new transaction starts with. Blank,
// not 0: a blank income basis or Spent proceeds means "use that hour's BTC
// price" (the server fills it); 0 would be saved as $0.
const TYPE_DEFAULTS: Partial<TransactionFormData> = {
  fee: 0,
  costBasisUSD: undefined,
  proceeds_usd: undefined,
  fmv_usd: undefined,
  grossProceedsUSD: 0,
  brokerReporting: "",
  // An account chosen for one type is none of another's (5.13)
  fromAccountId: undefined,
  toAccountId: undefined,
};

/** The transaction form: a new transaction, or `transactionId`'s to edit. */
const TransactionForm: React.FC<TransactionFormProps> = ({
  id,
  onDirtyChange,
  onSubmitSuccess,
  transactionId,
  onUpdateStatusChange,
}) => {
  const toast = useToast();
  const toastError = toast.error; // stable callback; `toast` itself changes per render
  // Accounts are the book's, by id (5.13): without it there's nothing to
  // pick or read a row back with, so the type's fields wait for it
  const { book, failed } = useAccounts();

  const form = useForm<TransactionFormData>({
    defaultValues: { timestamp: toDatetimeLocal(new Date()), ...TYPE_DEFAULTS },
  });
  const {
    register,
    handleSubmit,
    reset,
    getValues,
    setValue,
    formState: { errors, isDirty },
  } = form;

  const [currentType, setCurrentType] = useState<TransactionType | "">("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  // Set synchronously: the state above only disables the button on the next
  // render, so a double click used to save the transaction twice.
  const submittingRef = useRef(false);
  // A save or delete that changes an earlier tax year waits for the owner's
  // answer (#352): nothing is processing meanwhile
  const pastYears = usePastYearWarning();
  const working = isSubmitting && !pastYears.asking;

  // The transaction to edit, read back with the book once it's in.
  useEffect(() => {
    if (!transactionId || !book) return;
    let live = true; // a form closed meanwhile is left alone
    api.get<ITransactionRaw>(`/transactions/${transactionId}`)
      .then((res) => {
        if (!live) return;
        const tx = parseTransaction(res.data);
        const data = mapTransactionToFormData(tx, book);
        reset(data);
        for (const [name, text] of plainBtcText(data)) setValue(name, text);
        setCurrentType(tx.type);
      })
      .catch(() => {
        if (live) toastError("Failed to load transaction data.");
      });
    return () => {
      live = false;
    };
  }, [transactionId, book, reset, setValue, toastError]);

  // A new transaction starts blank; apart from the book's arrival, so a type
  // chosen while it loads is kept
  useEffect(() => {
    if (transactionId) return;
    reset({ timestamp: toDatetimeLocal(new Date()), ...TYPE_DEFAULTS });
    setCurrentType("");
  }, [transactionId, reset]);

  // A layout effect: the panel knows of a change before the next key or
  // click (a plain effect ran later, and an Escape at once closed the panel
  // without asking)
  useLayoutEffect(() => {
    onDirtyChange?.(isDirty);
  }, [isDirty, onDirtyChange]);

  useEffect(() => {
    onUpdateStatusChange?.(working);
  }, [working, onUpdateStatusChange]);

  useFieldAutofill(currentType, form, book);

  // A new type keeps what was typed but resets the type's own values.
  const onTransactionTypeChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const newType = e.target.value as TransactionType;
    setCurrentType(newType);
    reset({ ...getValues(), type: newType, ...TYPE_DEFAULTS });
  };

  const onSubmit: SubmitHandler<TransactionFormData> = async (data) => {
    if (submittingRef.current) return;
    // Without the book no account was chosen: nothing true to save
    if (!book) {
      if (failed) toast.error(ACCOUNTS_FAILED);
      return;
    }
    submittingRef.current = true;
    setIsSubmitting(true);
    try {
      const saved = await pastYears.attempt(transactionId ? "edit" : "add", (confirm) =>
        saveTransaction(data, book, transactionId, confirm));
      if (saved === null) return; // the owner cancelled: nothing saved, and the form keeps what was typed
      toast.success(saved);
      reset();
      setCurrentType("");
      onSubmitSuccess?.();
    } catch (error) {
      toast.error(saveFailedMessage(error, transactionId ? "update" : "create"));
    } finally {
      submittingRef.current = false;
      setIsSubmitting(false);
    }
  };

  const handleDeleteClick = async () => {
    if (!transactionId) return;
    const confirmed = window.confirm(
      "Are you sure you want to delete this transaction?"
    );
    if (!confirmed) return;

    setIsSubmitting(true);
    try {
      const deleted = await pastYears.attempt("delete", (confirm) => deleteTransaction(transactionId, confirm));
      if (deleted === null) return; // the owner cancelled: nothing deleted
      toast.success("Transaction deleted successfully!");
      reset();
      onSubmitSuccess?.();
    } catch (error) {
      // The server says why (e.g. a later sell spends this buy's BTC)
      const reason = serverReason(error);
      toast.error(reason ? `Failed to delete transaction: ${reason}` : "Failed to delete transaction. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <FormProvider {...form}>
      <form
        id={id || "transaction-form"}
        className="transaction-form"
        // handleSubmit only wraps onSubmit, which reads submittingRef at submit, not in render
        // eslint-disable-next-line react-hooks/refs
        onSubmit={handleSubmit(onSubmit)}
      >
        {working && (
          <div className="loading-row form-status">
            <div className="spinner"></div>
            <span>Processing transaction…</span>
          </div>
        )}

        <div className="form-fields-grid">
          <div className="field form-field-wide">
            <label htmlFor="tx-transaction-type">Transaction Type</label>
            <select
              id="tx-transaction-type"
              className="input"
              value={currentType}
              onChange={onTransactionTypeChange}
              required
              disabled={!!transactionId} // an edit keeps its type
            >
              <option value="">Select Transaction Type</option>
              <option value="Deposit">Deposit</option>
              <option value="Withdrawal">Withdrawal</option>
              <option value="Transfer">Transfer</option>
              <option value="Buy">Buy</option>
              <option value="Sell">Sell</option>
            </select>
          </div>

          <div className="field form-field-wide">
            <label htmlFor="tx-date-time">Date & Time</label>
            <input
              id="tx-date-time"
              type="datetime-local"
              step="1"
              className="input"
              {...register("timestamp", { required: "Date & Time is required" })}
            />
            {errors.timestamp && (
              <span className="field-error">{errors.timestamp.message}</span>
            )}
          </div>

          {failed && (currentType || transactionId) && <p className="field-error">{ACCOUNTS_FAILED}</p>}
          {book && <TypeFields type={currentType} book={book} transactionId={transactionId} />}
        </div>

        {/* Hidden delete trigger for TransactionPanel */}
        {transactionId && (
          <button
            id="trigger-form-delete"
            type="button"
            className="hidden-trigger"
            onClick={handleDeleteClick}
          />
        )}
      </form>
      {/* Outside the form: its buttons and box are the dialog's, never the form's */}
      {pastYears.question && <PastYearDialog {...pastYears.question} />}
    </FormProvider>
  );
};

export default TransactionForm;
