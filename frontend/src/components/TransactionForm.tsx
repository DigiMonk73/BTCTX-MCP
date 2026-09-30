import React, { useState, useEffect, useRef } from "react";
import { FormProvider, useForm, SubmitHandler } from "react-hook-form";
import axios from "axios";
import api from "../api";
import { useToast } from "../contexts/useToast";
import "../styles/transactionForm.css";
import { parseDecimal, parseTransaction } from "../utils/format";
import { localDatetimeToIso, mapTransactionToFormData, toDatetimeLocal } from "../utils/transactionForm";
import TypeFields from "./transactionForm/TypeFields";
import { saveFailedMessage, saveTransaction } from "./transactionForm/saveTransaction";
import { useFieldAutofill } from "./transactionForm/useFieldAutofill";

// What a change of type resets, and a new transaction starts with. Blank,
// not 0: a blank income basis or Spent proceeds means "use that day's BTC
// price" (the server fills it); 0 would be saved as $0.
const TYPE_DEFAULTS: Partial<TransactionFormData> = {
  fee: 0,
  costBasisUSD: undefined,
  proceeds_usd: undefined,
  fmv_usd: undefined,
  grossProceedsUSD: 0,
  brokerReporting: "",
  buyFromAccount: "Exchange",
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

  const form = useForm<TransactionFormData>({
    defaultValues: { timestamp: toDatetimeLocal(new Date()), ...TYPE_DEFAULTS },
  });
  const {
    register,
    handleSubmit,
    setValue,
    reset,
    getValues,
    formState: { errors, isDirty },
  } = form;

  const [currentType, setCurrentType] = useState<TransactionType | "">("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  // Set synchronously: the state above only disables the button on the next
  // render, so a double click used to save the transaction twice.
  const submittingRef = useRef(false);

  // Load the transaction to edit, or start a new one.
  useEffect(() => {
    if (transactionId) {
      api
        .get<ITransactionRaw>(`/transactions/${transactionId}`)
        .then((res) => {
          const tx = parseTransaction(res.data);
          reset(mapTransactionToFormData(tx));
          setCurrentType(tx.type);
        })
        .catch(() => {
          toastError("Failed to load transaction data.");
        });
    } else {
      reset({ timestamp: toDatetimeLocal(new Date()), ...TYPE_DEFAULTS });
      setCurrentType("");
    }
  }, [transactionId, reset, toastError]);

  useEffect(() => {
    onDirtyChange?.(isDirty);
  }, [isDirty, onDirtyChange]);

  useEffect(() => {
    onUpdateStatusChange?.(isSubmitting);
  }, [isSubmitting, onUpdateStatusChange]);

  useFieldAutofill(currentType, form);

  // A new type keeps what was typed but resets the type's own values.
  const onTransactionTypeChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const newType = e.target.value as TransactionType;
    setCurrentType(newType);
    reset({ ...getValues(), type: newType, ...TYPE_DEFAULTS });
  };

  // The FMV of a gift, donation or loss: amount x that day's price (or the
  // live price for a date not yet past).
  const handleRefreshFmv = async () => {
    try {
      const formVals = getValues();
      const txDate = new Date(localDatetimeToIso(formVals.timestamp));
      const priceResponse = txDate < new Date()
        ? await api.get(`/bitcoin/price/history?date=${txDate.toISOString().split("T")[0]}`)
        : await api.get("/bitcoin/price");

      const data = priceResponse.data;
      const btcPrice = data?.USD ? parseDecimal(data.USD) : 0;
      if (!btcPrice || btcPrice <= 0) {
        throw new Error("Invalid price data from API");
      }
      const newFmv = parseDecimal(formVals.amount || 0) * btcPrice;
      setValue("fmv_usd", Number(newFmv.toFixed(2)));
    } catch {
      toast.error("Failed to refresh FMV. Please try again.");
    }
  };

  const onSubmit: SubmitHandler<TransactionFormData> = async (data) => {
    if (submittingRef.current) return;
    submittingRef.current = true;
    setIsSubmitting(true);
    try {
      toast.success(await saveTransaction(data, transactionId));
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
    const confirmed = window.confirm(
      "Are you sure you want to delete this transaction?"
    );
    if (!confirmed) return;

    setIsSubmitting(true);
    try {
      await api.delete(`/transactions/${transactionId}`);
      toast.success("Transaction deleted successfully!");
      reset();
      onSubmitSuccess?.();
    } catch (error) {
      // The server says why (e.g. a later sell spends this buy's BTC)
      const detail = axios.isAxiosError<ApiErrorResponse>(error) ? error.response?.data?.detail : undefined;
      toast.error(detail ? `Failed to delete transaction: ${detail}` : "Failed to delete transaction. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <FormProvider {...form}>
      <form
        id={id || "transaction-form"}
        className="transaction-form"
        onSubmit={handleSubmit(onSubmit)}
      >
        {isSubmitting && (
          <div className="loading-row form-status">
            <div className="spinner"></div>
            <span>Processing transaction…</span>
          </div>
        )}

        <div className="form-fields-grid">
          <div className="field">
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

          <div className="field">
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

          <TypeFields type={currentType} onRefreshFmv={handleRefreshFmv} />
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
    </FormProvider>
  );
};

export default TransactionForm;
