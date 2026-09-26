// FILE: frontend/src/components/TransactionForm.tsx
import React, { useState, useEffect, useRef } from "react";
import { useForm, SubmitHandler } from "react-hook-form";
import axios from "axios";
import api from "../api";
import { useToast } from "../contexts/useToast";
import "../styles/transactionForm.css";
import { parseDecimal, formatUsd, parseTransaction } from "../utils/format";
import {
  buildTransactionPayload,
  localDatetimeToIso,
  mapTransactionToFormData,
  toDatetimeLocal,
} from "../utils/transactionForm";

/**
 * TransactionForm:
 * Now supports both "create new" and "edit existing" (transactionId).
 */
const TransactionForm: React.FC<TransactionFormProps> = ({
  id,
  onDirtyChange,
  onSubmitSuccess,
  transactionId,           // new prop
  onUpdateStatusChange,     // new prop
}) => {
  const toast = useToast();
  const toastError = toast.error; // stable callback; `toast` itself changes per render

  // Set up react-hook-form
  const {
    register,
    handleSubmit,
    watch,
    setValue,
    reset,
    getValues,
    formState: { errors, isDirty },
  } = useForm<TransactionFormData>({
    defaultValues: {
      // Minimal defaults to start
      timestamp: toDatetimeLocal(new Date()),
      fee: 0,
      // Blank, not 0: a blank income basis or Spent proceeds means "use that
      // day's BTC price" (the server fills it); 0 would be saved as $0.
      costBasisUSD: undefined,
      proceeds_usd: undefined,
      fmv_usd: undefined,

      // NEW: Initialize "grossProceedsUSD"
      grossProceedsUSD: 0,
      brokerReporting: "",

      // Default for Buy transactions: Exchange USD
      buyFromAccount: "Exchange",
    },
  });

  // Local state
  const [currentType, setCurrentType] = useState<TransactionType | "">("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  // Set synchronously: the state above only disables the button on the next
  // render, so a double click used to save the transaction twice.
  const submittingRef = useRef(false);

  // Watch various fields
  const accountVal = watch("account");
  const fromAccountVal = watch("fromAccount");
  const fromCurrencyVal = watch("fromCurrency");
  const amountFromVal = watch("amountFrom") || 0;
  const amountToVal = watch("amountTo") || 0;
  const purposeVal = watch("purpose");
  const proceedsUsdVal = watch("proceeds_usd");

  /**
   * Load existing transaction if we have a transactionId
   */
  useEffect(() => {
    if (transactionId) {
      api
        .get<ITransactionRaw>(`/transactions/${transactionId}`)
        .then((res) => {
          const tx = parseTransaction(res.data);
          const formData = mapTransactionToFormData(tx);
          reset(formData);
          setCurrentType(tx.type);
        })
        .catch(() => {
          toastError("Failed to load transaction data.");
        });
    } else {
      // If no transactionId => create mode
      reset({
        timestamp: toDatetimeLocal(new Date()),
        fee: 0,
        costBasisUSD: undefined,
        proceeds_usd: undefined,
        fmv_usd: undefined,
        grossProceedsUSD: 0,
        brokerReporting: "",
        buyFromAccount: "Exchange",
      });
      setCurrentType("");
    }
  }, [transactionId, reset, toastError]);

  /**
   * Notify parent about "dirty" form
   */
  useEffect(() => {
    onDirtyChange?.(isDirty);
  }, [isDirty, onDirtyChange]);

  /**
   * Notify parent about submission status
   */
  useEffect(() => {
    onUpdateStatusChange?.(isSubmitting);
  }, [isSubmitting, onUpdateStatusChange]);

  /**
   * If Deposit/Withdrawal => auto-set currency for Bank/Wallet
   */
  useEffect(() => {
    if (currentType === "Deposit" || currentType === "Withdrawal") {
      if (accountVal === "Bank") {
        setValue("currency", "USD");
      } else if (accountVal === "Wallet") {
        setValue("currency", "BTC");
      }
      // If account=Exchange => user picks currency
    }
  }, [currentType, accountVal, setValue]);

  /**
   * Transfer logic => auto-set "toAccount" & "toCurrency" based on "fromAccount"
   */
  useEffect(() => {
    if (currentType === "Transfer") {
      if (fromAccountVal === "Bank") {
        setValue("fromCurrency", "USD");
        setValue("toAccount", "Exchange");
        setValue("toCurrency", "USD");
      } else if (fromAccountVal === "Wallet") {
        setValue("fromCurrency", "BTC");
        setValue("toAccount", "Exchange");
        setValue("toCurrency", "BTC");
      } else if (fromAccountVal === "Exchange") {
        if (fromCurrencyVal === "USD") {
          setValue("toAccount", "Bank");
          setValue("toCurrency", "USD");
        } else if (fromCurrencyVal === "BTC") {
          setValue("toAccount", "Wallet");
          setValue("toCurrency", "BTC");
        }
      }
    }
  }, [currentType, fromAccountVal, fromCurrencyVal, setValue]);

  /**
   * Auto-calc fee for BTC Transfer: fee = (amountFrom - amountTo)
   */
  useEffect(() => {
    if (currentType === "Transfer" && fromCurrencyVal === "BTC") {
      const calcFee = amountFromVal - amountToVal;
      if (calcFee < 0) {
        setValue("fee", 0);
      } else {
        setValue("fee", Number(calcFee.toFixed(8)));
      }
    }
  }, [currentType, fromCurrencyVal, amountFromVal, amountToVal, setValue]);

  /**
   * onTransactionTypeChange:
   * When user picks a new type from the dropdown, reset some form fields.
   */
  const onTransactionTypeChange = (
    e: React.ChangeEvent<HTMLSelectElement>
  ) => {
    const newType = e.target.value as TransactionType;
    setCurrentType(newType);

    // Preserve existing, but reset certain fields
    const currentValues = getValues();
    reset({
      ...currentValues,
      type: newType,
      fee: 0,
      costBasisUSD: undefined,
      proceeds_usd: undefined,
      fmv_usd: undefined,
      grossProceedsUSD: 0,
      brokerReporting: "",
      buyFromAccount: "Exchange",
    });
  };

  /**
   * handleRefreshFmv:
   * Called when user clicks "Refresh" button for FMV. 
   */
  const handleRefreshFmv = async () => {
    try {
      const formVals = getValues();
      const isoTimestamp = localDatetimeToIso(formVals.timestamp);
      const txDate = new Date(isoTimestamp);

      const now = new Date();
      const isBackdated = txDate < now;

      let priceResponse;
      if (isBackdated) {
        const dateStr = txDate.toISOString().split("T")[0]; // e.g. "2025-03-28"
        priceResponse = await api.get(`/bitcoin/price/history?date=${dateStr}`);
      } else {
        priceResponse = await api.get("/bitcoin/price");
      }

      const data = priceResponse.data;
      const btcPrice = data?.USD ? parseDecimal(data.USD) : 0;
      if (!btcPrice || btcPrice <= 0) {
        throw new Error("Invalid price data from API");
      }

      const amountBtc = parseDecimal(formVals.amount || 0);
      const newFmv = amountBtc * btcPrice;

      setValue("fmv_usd", Number(newFmv.toFixed(2)));
    } catch {
      toast.error("Failed to refresh FMV. Please try again.");
    }
  };

  /**
   * onSubmit:
   * Either create a new transaction or update the existing one.
   *
   * // NEW: GROSS PROCEEDS FOR SELL
   *  If type=Sell => we now pass "gross_proceeds_usd" as well, which the backend
   *  will use to compute net (proceeds_usd).
   */
  const onSubmit: SubmitHandler<TransactionFormData> = async (data) => {
    if (submittingRef.current) return;
    submittingRef.current = true;
    setIsSubmitting(true);
    try {
      const payload = buildTransactionPayload(data);

      if (transactionId) {
        // --- EDITING existing transaction ---
        const response = await api.put(`/transactions/${transactionId}`, payload);
        if (response.status !== 200) {
          throw new Error(`Update failed with status ${response.status}`);
        }
        const updatedTx = response.data as ITransactionRaw;
        const rg = updatedTx.realized_gain_usd
          ? parseDecimal(updatedTx.realized_gain_usd)
          : 0;

        if (rg !== 0) {
          const sign = rg >= 0 ? "+" : "";
          toast.success(
            `Transaction updated! Realized Gain: ${sign}${formatUsd(rg)}`
          );
        } else {
          toast.success("Transaction updated successfully!");
        }
      } else {
        // --- CREATING new transaction ---
        const createPayload: ICreateTransactionPayload = {
          ...payload,
          is_locked: false,
        };
        const response = await api.post("/transactions", createPayload);
        const createdTx = response.data as ITransactionRaw;
        const rg = createdTx.realized_gain_usd
          ? parseDecimal(createdTx.realized_gain_usd)
          : 0;

        if (rg !== 0) {
          const sign = rg >= 0 ? "+" : "";
          toast.success(
            `Transaction created! Realized Gain: ${sign}${formatUsd(rg)}`
          );
        } else {
          toast.success("Transaction created successfully!");
        }
      }

      // Reset & notify success
      reset();
      setCurrentType("");
      onSubmitSuccess?.();
    } catch (error) {
      const action = transactionId ? "update" : "create";
      if (axios.isAxiosError<ApiErrorResponse>(error)) {
        const detailMsg =
          error.response?.data?.detail || error.message || "Error";
        toast.error(`Failed to ${action} transaction: ${detailMsg}`);
      } else if (error instanceof Error) {
        toast.error(`Failed to ${action} transaction: ${error.message}`);
      } else {
        toast.error(`An unexpected error occurred while ${action}ing the transaction.`);
      }
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
    } catch {
      toast.error("Failed to delete transaction. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  };

  /**
   * renderDynamicFields:
   * Renders form controls for each transaction type.
   * // NEW: For "Sell" we show "Gross Proceeds (USD)" instead of "Amount USD"
   */
  // Form 1099-DA override (Sell, and Spent BTC withdrawals)
  const renderBrokerReportingField = () => (
    <div className="form-group">
      <label htmlFor="tx-broker-reporting">Broker form (1099-DA / 1099-B):</label>
      <select id="tx-broker-reporting" className="form-control" {...register("brokerReporting")}>
        <option value="">Automatic</option>
        <option value="none">Not on a broker form</option>
        <option value="proceeds">Proceeds only (no basis)</option>
        <option value="basis">Proceeds and basis</option>
      </select>
      <small className="form-hint">
        Picks the Form 8949 box. Leave on Automatic unless the form your broker
        sent says otherwise.
      </small>
    </div>
  );

  const renderDynamicFields = () => {
    switch (currentType) {
      case "Deposit": {
        const account = watch("account");
        const currency = watch("currency");

        // Show cost basis if BTC deposit into Wallet or Exchange
        const showCostBasisField =
          currentType === "Deposit" &&
          currency === "BTC" &&
          (account === "Wallet" || account === "Exchange");

        // Show source if BTC deposit into Wallet/Exchange
        const showSource =
          account === "Wallet" ||
          (account === "Exchange" && currency === "BTC");

        // Income: basis = market value at receipt (the server fills a blank one)
        const isIncome = ["Income", "Interest", "Reward"].includes(watch("source") ?? "");

        return (
          <>
            {/* Account */}
            <div className="form-group">
              <label htmlFor="tx-account">Account:</label>
              <select
                id="tx-account"
                className="form-control"
                {...register("account", { required: true })}
              >
                <option value="">Select Account</option>
                <option value="Bank">Bank Account</option>
                <option value="Wallet">Bitcoin Wallet</option>
                <option value="Exchange">Exchange</option>
              </select>
              {errors.account && (
                <span className="error-text">Please select an account</span>
              )}
            </div>

            {/* Currency */}
            <div className="form-group">
              <label htmlFor="tx-currency">Currency:</label>
              {account === "Exchange" ? (
                <select
                  id="tx-currency"
                  className="form-control"
                  {...register("currency", { required: true })}
                >
                  <option value="">Select Currency</option>
                  <option value="USD">USD</option>
                  <option value="BTC">BTC</option>
                </select>
              ) : (
                <input
                  id="tx-currency"
                  type="text"
                  className="form-control"
                  {...register("currency")}
                  readOnly
                />
              )}
              {errors.currency && (
                <span className="error-text">Currency is required</span>
              )}
            </div>

            {/* Amount */}
            <div className="form-group">
              <label htmlFor="tx-amount">Amount:</label>
              <input
                id="tx-amount"
                type="number"
                step="0.00000001"
                className="form-control"
                {...register("amount", {
                  required: true,
                  valueAsNumber: true,
                })}
              />
              {errors.amount && (
                <span className="error-text">Amount is required</span>
              )}
            </div>

            {/* Source */}
            {showSource && (
              <div className="form-group">
                <label htmlFor="tx-source">Source:</label>
                <select
                  id="tx-source"
                  className="form-control"
                  {...register("source", { required: true })}
                >
                  <option value="N/A">N/A</option>
                  <option value="MyBTC">MyBTC</option>
                  <option value="Gift">Gift</option>
                  <option value="Income">Income</option>
                  <option value="Interest">Interest</option>
                  <option value="Reward">Reward</option>
                </select>
              </div>
            )}

            {/* Cost Basis if BTC deposit */}
            {showCostBasisField && (
              <div className="form-group">
                <label htmlFor="tx-cost-basis-usd">Cost Basis (USD):</label>
                <input
                  id="tx-cost-basis-usd"
                  type="number"
                  step="0.01"
                  className="form-control"
                  {...register("costBasisUSD", { valueAsNumber: true })}
                />
                <small className="form-hint">
                  {isIncome
                    ? "Its USD value when you received it (also your income). Leave blank to use that day's BTC price."
                    : "If you paid a miner fee in BTC externally, add its USD value here."}
                </small>
              </div>
            )}
          </>
        );
      }

      case "Withdrawal": {
        const account = watch("account");
        const currency = watch("currency");
        const feeLabel = currency === "BTC" ? "Fee (BTC)" : "Fee (USD)";
        const showPurpose =
          account === "Wallet" ||
          (account === "Exchange" && currency === "BTC");

        // For BTC only, we show proceeds + possible FMV
        const showBtcFields = currency === "BTC";

        const isSpecialPurpose =
          purposeVal === "Gift" ||
          purposeVal === "Donation" ||
          purposeVal === "Lost";

        return (
          <>
            {/* Account */}
            <div className="form-group">
              <label htmlFor="tx-account">Account:</label>
              <select
                id="tx-account"
                className="form-control"
                {...register("account", { required: true })}
              >
                <option value="">Select Account</option>
                <option value="Bank">Bank Account</option>
                <option value="Wallet">Bitcoin Wallet</option>
                <option value="Exchange">Exchange</option>
              </select>
              {errors.account && (
                <span className="error-text">Please select an account</span>
              )}
            </div>

            {/* Currency */}
            <div className="form-group">
              <label htmlFor="tx-currency">Currency:</label>
              {account === "Exchange" ? (
                <select
                  id="tx-currency"
                  className="form-control"
                  {...register("currency", { required: true })}
                >
                  <option value="">Select Currency</option>
                  <option value="USD">USD</option>
                  <option value="BTC">BTC</option>
                </select>
              ) : (
                <input
                  id="tx-currency"
                  type="text"
                  className="form-control"
                  {...register("currency")}
                  readOnly
                />
              )}
              {errors.currency && (
                <span className="error-text">Currency is required</span>
              )}
            </div>

            {/* Amount */}
            <div className="form-group">
              <label htmlFor="tx-amount">Amount:</label>
              <input
                id="tx-amount"
                type="number"
                step="0.00000001"
                className="form-control"
                {...register("amount", {
                  required: true,
                  valueAsNumber: true,
                })}
              />
              {errors.amount && (
                <span className="error-text">Amount is required</span>
              )}
            </div>

            {/* Purpose (BTC only) */}
            {showPurpose && (
              <div className="form-group">
                <label htmlFor="tx-purpose">Purpose (BTC only):</label>
                <select
                  id="tx-purpose"
                  className="form-control"
                  {...register("purpose", { required: true })}
                >
                  <option value="">Select Purpose</option>
                  <option value="Spent">Spent</option>
                  <option value="Gift">Gift</option>
                  <option value="Donation">Donation</option>
                  <option value="Lost">Lost</option>
                </select>
              </div>
            )}

            {/* Fee */}
            <div className="form-group">
              <label htmlFor="tx-fee">{feeLabel}:</label>
              <input
                id="tx-fee"
                type="number"
                step="0.00000001"
                className="form-control"
                {...register("fee", { valueAsNumber: true })}
              />
            </div>

            {/* For BTC withdrawals: proceeds + FMV */}
            {showBtcFields && (
              <>
                {/* Proceeds */}
                <div className="form-group">
                  <label htmlFor="tx-proceeds-usd">Proceeds (USD):</label>
                  <input
                    id="tx-proceeds-usd"
                    type="number"
                    step="0.01"
                    className="form-control"
                    {...register("proceeds_usd", { valueAsNumber: true })}
                    readOnly={isSpecialPurpose}
                  />
                  {purposeVal === "Spent" && (proceedsUsdVal == null || Number.isNaN(proceedsUsdVal)) && (
                    <small className="form-hint">
                      Leave blank to use that day's BTC price as the proceeds.
                    </small>
                  )}
                  {purposeVal === "Spent" && proceedsUsdVal === 0 && (
                    <div className="form-warning">
                      <strong>Warning:</strong> You selected "Spent" but "Proceeds (USD)" is 0.
                    </div>
                  )}
                </div>

                {purposeVal === "Spent" && renderBrokerReportingField()}

                {/* FMV for Gift/Donation/Lost */}
                {isSpecialPurpose && (
                  <div className="form-group">
                    <label htmlFor="tx-fmv-usd">FMV (USD):</label>
                    <div className="form-input-row">
                      <input
                        id="tx-fmv-usd"
                        type="number"
                        step="0.01"
                        className="form-control"
                        {...register("fmv_usd", { valueAsNumber: true })}
                      />
                      <button
                        type="button"
                        onClick={handleRefreshFmv}
                        className="refresh-button"
                      >
                        Refresh
                      </button>
                    </div>
                    <small className="form-hint">
                      Estimated fair market value at the time of gift/donation/lost.
                    </small>
                  </div>
                )}
              </>
            )}
          </>
        );
      }

      case "Transfer": {
        const fromAccount = watch("fromAccount");
        const fromCurr = watch("fromCurrency");
        return (
          <>
            {/* From Account */}
            <div className="form-group">
              <label htmlFor="tx-from-account">From Account:</label>
              <select
                id="tx-from-account"
                className="form-control"
                {...register("fromAccount", { required: true })}
              >
                <option value="">Select From Account</option>
                <option value="Bank">Bank Account</option>
                <option value="Wallet">Bitcoin Wallet</option>
                <option value="Exchange">Exchange</option>
              </select>
              {errors.fromAccount && (
                <span className="error-text">From Account is required</span>
              )}
            </div>

            {/* From Currency */}
            <div className="form-group">
              <label htmlFor="tx-from-currency">From Currency:</label>
              {fromAccount === "Exchange" ? (
                <select
                  id="tx-from-currency"
                  className="form-control"
                  {...register("fromCurrency", { required: true })}
                >
                  <option value="">Select Currency</option>
                  <option value="USD">USD</option>
                  <option value="BTC">BTC</option>
                </select>
              ) : (
                <input
                  id="tx-from-currency"
                  type="text"
                  className="form-control"
                  {...register("fromCurrency")}
                  readOnly
                />
              )}
              {errors.fromCurrency && (
                <span className="error-text">From Currency is required</span>
              )}
            </div>

            {/* Amount (From) */}
            <div className="form-group">
              <label htmlFor="tx-amount-from">Amount (From):</label>
              <input
                id="tx-amount-from"
                type="number"
                step="0.00000001"
                className="form-control"
                {...register("amountFrom", {
                  required: true,
                  valueAsNumber: true,
                })}
              />
              {errors.amountFrom && (
                <span className="error-text">Amount (From) is required</span>
              )}
            </div>

            {/* To Account */}
            <div className="form-group">
              <label htmlFor="tx-to-account">To Account:</label>
              <input
                id="tx-to-account"
                type="text"
                className="form-control"
                {...register("toAccount")}
                readOnly
              />
            </div>

            {/* To Currency */}
            <div className="form-group">
              <label htmlFor="tx-to-currency">To Currency:</label>
              <input
                id="tx-to-currency"
                type="text"
                className="form-control"
                {...register("toCurrency")}
                readOnly
              />
            </div>

            {/* Amount (To) */}
            <div className="form-group">
              <label htmlFor="tx-amount-to">Amount (To):</label>
              <input
                id="tx-amount-to"
                type="number"
                step="0.00000001"
                className="form-control"
                {...register("amountTo", {
                  required: true,
                  valueAsNumber: true,
                })}
              />
              {errors.amountTo && (
                <span className="error-text">Amount (To) is required</span>
              )}
            </div>

            {/* Fee auto-calc if BTC */}
            {fromCurr === "BTC" ? (
              <div className="form-group">
                <label htmlFor="tx-fee-btc">Fee (BTC):</label>
                <input
                  id="tx-fee-btc"
                  type="number"
                  step="0.00000001"
                  className="form-control"
                  {...register("fee", { valueAsNumber: true })}
                  readOnly
                />
              </div>
            ) : (
              <div className="form-group">
                <label htmlFor="tx-fee-usd">Fee (USD):</label>
                <input
                  id="tx-fee-usd"
                  type="number"
                  step="0.01"
                  className="form-control"
                  defaultValue={0}
                  {...register("fee", { valueAsNumber: true })}
                />
              </div>
            )}
          </>
        );
      }

      case "Buy": {
        return (
          <>
            {/* Source Account: Bank or Exchange */}
            <div className="form-group">
              <label htmlFor="tx-from-account">From Account:</label>
              <select
                id="tx-from-account"
                className="form-control"
                {...register("buyFromAccount", { required: true })}
              >
                <option value="Exchange">Exchange USD</option>
                <option value="Bank">Bank (auto-buy)</option>
              </select>
              <small className="form-hint">
                Select where the USD is coming from.
              </small>
            </div>

            {/* Amount USD */}
            <div className="form-group">
              <label htmlFor="tx-amount-usd">Amount USD:</label>
              <input
                id="tx-amount-usd"
                type="number"
                step="0.01"
                className="form-control"
                {...register("amountUSD", {
                  required: true,
                  valueAsNumber: true,
                })}
              />
              {errors.amountUSD && (
                <span className="error-text">Amount USD is required</span>
              )}
            </div>

            {/* Amount BTC */}
            <div className="form-group">
              <label htmlFor="tx-amount-btc">Amount BTC:</label>
              <input
                id="tx-amount-btc"
                type="number"
                step="0.00000001"
                className="form-control"
                {...register("amountBTC", {
                  required: true,
                  valueAsNumber: true,
                })}
              />
              {errors.amountBTC && (
                <span className="error-text">Amount BTC is required</span>
              )}
            </div>

            {/* Fee (USD) */}
            <div className="form-group">
              <label htmlFor="tx-fee-usd">Fee (USD):</label>
              <input
                id="tx-fee-usd"
                type="number"
                step="0.00000001"
                className="form-control"
                {...register("fee", { valueAsNumber: true })}
              />
            </div>
          </>
        );
      }

      case "Sell": {
        return (
          <>
            {/* Account = Exchange */}
            <div className="form-group">
              <label htmlFor="tx-account">Account:</label>
              <input
                id="tx-account"
                type="text"
                className="form-control"
                value="Exchange"
                {...register("account")}
                readOnly
              />
            </div>

            {/* Amount BTC */}
            <div className="form-group">
              <label htmlFor="tx-amount-btc">Amount BTC:</label>
              <input
                id="tx-amount-btc"
                type="number"
                step="0.00000001"
                className="form-control"
                {...register("amountBTC", {
                  required: true,
                  valueAsNumber: true,
                })}
              />
              {errors.amountBTC && (
                <span className="error-text">Amount BTC is required</span>
              )}
            </div>

            {/* NEW: GROSS PROCEEDS (USD) */}
            <div className="form-group">
              <label htmlFor="tx-gross-proceeds-usd">Gross Proceeds (USD):</label>
              <input
                id="tx-gross-proceeds-usd"
                type="number"
                step="0.01"
                className="form-control"
                {...register("grossProceedsUSD", {
                  required: true,
                  valueAsNumber: true,
                })}
              />
              {errors.grossProceedsUSD && (
                <span className="error-text">Gross proceeds is required</span>
              )}
              <small className="form-hint">
                The backend will subtract fees to calculate net proceeds.
              </small>
            </div>

            {/* Fee (USD) */}
            <div className="form-group">
              <label htmlFor="tx-fee-usd">Fee (USD):</label>
              <input
                id="tx-fee-usd"
                type="number"
                step="0.00000001"
                className="form-control"
                {...register("fee", { valueAsNumber: true })}
              />
            </div>

            {renderBrokerReportingField()}
          </>
        );
      }

      default:
        return null; // If type not chosen yet
    }
  };

  // ------------------------------------------------------------------------
  // Actual render
  // ------------------------------------------------------------------------
  return (
    <form
      id={id || "transaction-form"}
      className="transaction-form"
      onSubmit={handleSubmit(onSubmit)}
    >
      {/* Optional spinner if isSubmitting */}
      {isSubmitting && (
        <div className="spinner-container">
          <div className="spinner"></div>
          <p>Processing transaction...</p>
        </div>
      )}

      <div className="form-fields-grid">
        {/* Transaction Type */}
        <div className="form-group">
          <label htmlFor="tx-transaction-type">Transaction Type:</label>
          <select
            id="tx-transaction-type"
            className="form-control"
            value={currentType}
            onChange={onTransactionTypeChange}
            required
            disabled={!!transactionId} // if editing, lock the type
          >
            <option value="">Select Transaction Type</option>
            <option value="Deposit">Deposit</option>
            <option value="Withdrawal">Withdrawal</option>
            <option value="Transfer">Transfer</option>
            <option value="Buy">Buy</option>
            <option value="Sell">Sell</option>
          </select>
        </div>

        {/* Date & Time */}
        <div className="form-group">
          <label htmlFor="tx-date-time">Date & Time:</label>
          <input
            id="tx-date-time"
            type="datetime-local"
            step="1"
            className="form-control"
            {...register("timestamp", { required: "Date & Time is required" })}
          />
          {errors.timestamp && (
            <span className="error-text">{errors.timestamp.message}</span>
          )}
        </div>

        {/* Dynamic transaction-type-specific fields */}
        {renderDynamicFields()}
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
  );
};

export default TransactionForm;
