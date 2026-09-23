// FILE: frontend/src/components/TransactionForm.tsx
import React, { useState, useEffect } from "react";
import { useForm, SubmitHandler } from "react-hook-form";
import axios from "axios";
import api from "../api";
import { useToast } from "../contexts/useToast";
import "../styles/transactionForm.css";
import { parseDecimal, formatUsd, parseTransaction } from "../utils/format";

/**
 * localDatetimeToIso:
 * Converts "datetime-local" (e.g. "2025-03-01T12:00")
 * to a full ISO8601 string for the backend.
 */
function localDatetimeToIso(localDatetime: string): string {
  return new Date(localDatetime).toISOString();
}

// Hardcoded account IDs
const BANK_ID = 1;
const EXTERNAL_ID = 99;
const EXCHANGE_USD_ID = 3;
const EXCHANGE_BTC_ID = 4;

/**
 * mapAccountToId:
 * Convert an AccountType + Currency to the numeric ID recognized by the backend.
 */
function mapAccountToId(account?: AccountType, currency?: Currency): number {
  if (account === "Bank") return 1;
  if (account === "Wallet") return 2;
  if (account === "Exchange") {
    return currency === "BTC" ? EXCHANGE_BTC_ID : EXCHANGE_USD_ID;
  }
  return 0;
}

/**
 * mapDoubleEntryAccounts:
 * Single-entry style => from/to IDs for the ledger.
 */
function mapDoubleEntryAccounts(data: TransactionFormData): IAccountMapping {
  switch (data.type) {
    case "Deposit":
      return {
        from_account_id: EXTERNAL_ID,
        to_account_id: mapAccountToId(data.account, data.currency),
      };
    case "Withdrawal":
      return {
        from_account_id: mapAccountToId(data.account, data.currency),
        to_account_id: EXTERNAL_ID,
      };
    case "Transfer":
      return {
        from_account_id: mapAccountToId(data.fromAccount, data.fromCurrency),
        to_account_id: mapAccountToId(data.toAccount, data.toCurrency),
      };
    case "Buy":
      return {
        from_account_id: data.buyFromAccount === "Bank" ? BANK_ID : EXCHANGE_USD_ID,
        to_account_id: EXCHANGE_BTC_ID,
      };
    case "Sell":
      return {
        from_account_id: EXCHANGE_BTC_ID,
        to_account_id: EXCHANGE_USD_ID,
      };
    default:
      return { from_account_id: 0, to_account_id: 0 };
  }
}

/**
 * mapTransactionToFormData:
 * Converts an ITransaction (fetched from backend) into TransactionFormData
 * so we can populate the form fields in edit mode.
 *
 * // NEW: GROSS PROCEEDS FOR SELL
 * We read tx.gross_proceeds_usd (if present) into 'grossProceedsUSD' for the user to see.
 */
function mapTransactionToFormData(tx: ITransaction): TransactionFormData {
  // Common fields
  const baseData: TransactionFormData = {
    type: tx.type,
    timestamp: new Date(tx.timestamp).toISOString().slice(0, 16), // for datetime-local
    fee: tx.fee_amount ?? 0,
    costBasisUSD: tx.cost_basis_usd ?? 0,
    proceeds_usd: tx.proceeds_usd ?? 0,
    fmv_usd: tx.fmv_usd ?? 0,

    // NEW: GROSS PROCEEDS FOR SELL
    grossProceedsUSD: tx.gross_proceeds_usd ?? 0,
  };

  // Helper to convert account_id => "Bank", "Wallet", "Exchange", etc.
  const accountIdToType = (id: number): AccountType => {
    switch (id) {
      case 1:
        return "Bank";
      case 2:
        return "Wallet";
      case 3:
      case 4:
        return "Exchange";
      default:
        return "External";
    }
  };

  // Helper to guess currency from ID
  const getCurrencyFromAccountId = (id: number): Currency =>
    id === 1 || id === 3 ? "USD" : "BTC";

  switch (tx.type) {
    case "Deposit": {
      const toAcctId = tx.to_account_id ?? 0;
      return {
        ...baseData,
        account: accountIdToType(toAcctId),
        currency: getCurrencyFromAccountId(toAcctId),
        amount: tx.amount,
        source: (tx.source ?? "N/A") as DepositSource,
      };
    }
    case "Withdrawal": {
      const fromAcctId = tx.from_account_id ?? 0;
      return {
        ...baseData,
        account: accountIdToType(fromAcctId),
        currency: getCurrencyFromAccountId(fromAcctId),
        amount: tx.amount,
        purpose: (tx.purpose ?? "N/A") as WithdrawalPurpose,
        // Stored proceeds_usd is net of the BTC fee; edit the user's gross
        proceeds_usd: tx.gross_proceeds_usd ?? tx.proceeds_usd ?? 0,
      };
    }
    case "Transfer": {
      const fromAcctId = tx.from_account_id ?? 0;
      const toAcctId = tx.to_account_id ?? 0;
      const fromAccount = accountIdToType(fromAcctId);
      const toAccount = accountIdToType(toAcctId);
      const fromCurrency = getCurrencyFromAccountId(fromAcctId);
      const toCurrency = getCurrencyFromAccountId(toAcctId);

      return {
        ...baseData,
        fromAccount,
        toAccount,
        fromCurrency,
        toCurrency,
        amountFrom: tx.amount,
        // If it was BTC with a fee, "amountTo" is (amount - fee).
        amountTo:
          tx.type === "Transfer" && fromCurrency === "BTC"
            ? tx.amount - (tx.fee_amount ?? 0)
            : tx.amount,
      };
    }
    case "Buy": {
      // Determine if Buy was from Bank (ID 1) or Exchange USD (ID 3)
      const buyFromAccount = tx.from_account_id === 1 ? "Bank" : "Exchange";
      return {
        ...baseData,
        account: "Exchange",
        buyFromAccount,
        amountUSD: tx.cost_basis_usd ?? 0,
        amountBTC: tx.amount,
      };
    }
    case "Sell":
      return {
        ...baseData,
        account: "Exchange",
        amountBTC: tx.amount,

        // OLD: form used "amountUSD" for net proceeds
        // NEW: we treat "amountUSD" as "grossProceedsUSD" for user input
        grossProceedsUSD: tx.gross_proceeds_usd ?? tx.proceeds_usd ?? 0,
      };
    default:
      // Return the base for safety
      return baseData;
  }
}

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
      timestamp: new Date().toISOString().slice(0, 16),
      fee: 0,
      costBasisUSD: 0,
      proceeds_usd: 0,
      fmv_usd: 0,

      // NEW: Initialize "grossProceedsUSD"
      grossProceedsUSD: 0,

      // Default for Buy transactions: Exchange USD
      buyFromAccount: "Exchange",
    },
  });

  // Local state
  const [currentType, setCurrentType] = useState<TransactionType | "">("");
  const [feeInUsdDisplay, setFeeInUsdDisplay] = useState<number>(0);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Watch various fields
  const accountVal = watch("account");
  const fromAccountVal = watch("fromAccount");
  const fromCurrencyVal = watch("fromCurrency");
  const amountFromVal = watch("amountFrom") || 0;
  const amountToVal = watch("amountTo") || 0;
  const purposeVal = watch("purpose");
  const proceedsUsdVal = watch("proceeds_usd") || 0;

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
        timestamp: new Date().toISOString().slice(0, 16),
        fee: 0,
        costBasisUSD: 0,
        proceeds_usd: 0,
        fmv_usd: 0,
        grossProceedsUSD: 0,
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
        const feeBtc = Number(calcFee.toFixed(8));
        setValue("fee", feeBtc);
        // Show approximate USD
        const mockBtcPrice = 30000; // or some dynamic price
        const approxUsd = feeBtc * mockBtcPrice;
        setFeeInUsdDisplay(Number(approxUsd.toFixed(2)));
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
      costBasisUSD: 0,
      proceeds_usd: 0,
      fmv_usd: 0,
      grossProceedsUSD: 0,
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
    setIsSubmitting(true);
    try {
      // 1) If BTC withdrawal & user didn't provide proceeds, default to 0
      if (
        data.type === "Withdrawal" &&
        data.currency === "BTC" &&
        !data.proceeds_usd
      ) {
        data.proceeds_usd = 0;
      }

      // 2) from/to IDs
      const { from_account_id, to_account_id } = mapDoubleEntryAccounts(data);

      // 3) Convert datetime => ISO
      const isoTimestamp = localDatetimeToIso(data.timestamp);

      // 4) Prepare fields for the payload
      let amount = 0;
      let feeCurrency: Currency = "USD";
      let source: string | undefined;
      let purpose: string | undefined;
      let cost_basis_usd = 0;
      let proceeds_usd: number | undefined;
      let fmv_usd: number | undefined;
      let gross_proceeds_usd: number | undefined; // <-- new

      switch (data.type) {
        case "Deposit":
          amount = parseDecimal(data.amount);
          feeCurrency = data.currency === "BTC" ? "BTC" : "USD";
          source = data.source && data.source !== "N/A" ? data.source : "N/A";
          if (
            data.currency === "BTC" &&
            (data.account === "Wallet" || data.account === "Exchange")
          ) {
            cost_basis_usd = parseDecimal(data.costBasisUSD);
          }
          break;

        case "Withdrawal":
          amount = parseDecimal(data.amount);
          feeCurrency = data.currency === "BTC" ? "BTC" : "USD";
          purpose = data.purpose && data.purpose !== "N/A" ? data.purpose : "N/A";
          proceeds_usd = parseDecimal(data.proceeds_usd);
          fmv_usd = parseDecimal(data.fmv_usd);
          break;

        case "Transfer":
          amount = parseDecimal(data.amountFrom);
          feeCurrency = data.fromCurrency === "BTC" ? "BTC" : "USD";
          break;

        case "Buy":
          amount = parseDecimal(data.amountBTC);
          feeCurrency = "USD";
          cost_basis_usd = parseDecimal(data.amountUSD);
          break;

        case "Sell":
          // NEW: we interpret "amountBTC" as the BTC being sold
          amount = parseDecimal(data.amountBTC);
          feeCurrency = "USD";

          // Instead of storing net proceeds in "proceeds_usd," we store user input as "gross_proceeds_usd"
          gross_proceeds_usd = parseDecimal(data.grossProceedsUSD);
          break;
      }

      // 5) Build payload
      const payload: Omit<ICreateTransactionPayload, "is_locked"> = {
        type: data.type,
        timestamp: isoTimestamp,
        from_account_id,
        to_account_id,
        amount,
        fee_amount: parseDecimal(data.fee),
        fee_currency: feeCurrency,
        cost_basis_usd,
        proceeds_usd,   // might be undefined if Sell
        gross_proceeds_usd, // <-- new field for Sell
        fmv_usd,
        source,
        purpose,
      };

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

        return (
          <>
            {/* Account */}
            <div className="form-group">
              <label>Account:</label>
              <select
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
              <label>Currency:</label>
              {account === "Exchange" ? (
                <select
                  className="form-control"
                  {...register("currency", { required: true })}
                >
                  <option value="">Select Currency</option>
                  <option value="USD">USD</option>
                  <option value="BTC">BTC</option>
                </select>
              ) : (
                <input
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
              <label>Amount:</label>
              <input
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
                <label>Source:</label>
                <select
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
                <label>Cost Basis (USD):</label>
                <input
                  type="number"
                  step="0.01"
                  className="form-control"
                  {...register("costBasisUSD", { valueAsNumber: true })}
                />
                <small className="form-hint">
                  If you paid a miner fee in BTC externally, add its USD value here.
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
              <label>Account:</label>
              <select
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
              <label>Currency:</label>
              {account === "Exchange" ? (
                <select
                  className="form-control"
                  {...register("currency", { required: true })}
                >
                  <option value="">Select Currency</option>
                  <option value="USD">USD</option>
                  <option value="BTC">BTC</option>
                </select>
              ) : (
                <input
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
              <label>Amount:</label>
              <input
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
                <label>Purpose (BTC only):</label>
                <select
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
              <label>{feeLabel}:</label>
              <input
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
                  <label>Proceeds (USD):</label>
                  <input
                    type="number"
                    step="0.01"
                    className="form-control"
                    {...register("proceeds_usd", { valueAsNumber: true })}
                    readOnly={isSpecialPurpose}
                  />
                  {purposeVal === "Spent" && proceedsUsdVal === 0 && (
                    <div className="form-warning">
                      <strong>Warning:</strong> You selected "Spent" but "Proceeds (USD)" is 0.
                    </div>
                  )}
                </div>

                {/* FMV for Gift/Donation/Lost */}
                {isSpecialPurpose && (
                  <div className="form-group">
                    <label>FMV (USD):</label>
                    <div className="form-input-row">
                      <input
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
              <label>From Account:</label>
              <select
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
              <label>From Currency:</label>
              {fromAccount === "Exchange" ? (
                <select
                  className="form-control"
                  {...register("fromCurrency", { required: true })}
                >
                  <option value="">Select Currency</option>
                  <option value="USD">USD</option>
                  <option value="BTC">BTC</option>
                </select>
              ) : (
                <input
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
              <label>Amount (From):</label>
              <input
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
              <label>To Account:</label>
              <input
                type="text"
                className="form-control"
                {...register("toAccount")}
                readOnly
              />
            </div>

            {/* To Currency */}
            <div className="form-group">
              <label>To Currency:</label>
              <input
                type="text"
                className="form-control"
                {...register("toCurrency")}
                readOnly
              />
            </div>

            {/* Amount (To) */}
            <div className="form-group">
              <label>Amount (To):</label>
              <input
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
                <label>Fee (BTC):</label>
                <input
                  type="number"
                  step="0.00000001"
                  className="form-control"
                  {...register("fee", { valueAsNumber: true })}
                  readOnly
                />
                {feeInUsdDisplay > 0 && (
                  <small className="approx-value">
                    (~ ${feeInUsdDisplay} USD)
                  </small>
                )}
              </div>
            ) : (
              <div className="form-group">
                <label>Fee (USD):</label>
                <input
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
              <label>From Account:</label>
              <select
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
              <label>Amount USD:</label>
              <input
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
              <label>Amount BTC:</label>
              <input
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
              <label>Fee (USD):</label>
              <input
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
              <label>Account:</label>
              <input
                type="text"
                className="form-control"
                value="Exchange"
                {...register("account")}
                readOnly
              />
            </div>

            {/* Amount BTC */}
            <div className="form-group">
              <label>Amount BTC:</label>
              <input
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
              <label>Gross Proceeds (USD):</label>
              <input
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
              <label>Fee (USD):</label>
              <input
                type="number"
                step="0.00000001"
                className="form-control"
                {...register("fee", { valueAsNumber: true })}
              />
            </div>
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
          <label>Transaction Type:</label>
          <select
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
          <label>Date & Time:</label>
          <input
            type="datetime-local"
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
