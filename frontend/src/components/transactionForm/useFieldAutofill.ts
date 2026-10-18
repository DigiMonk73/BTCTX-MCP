import { useEffect } from "react";
import type { UseFormReturn } from "react-hook-form";
import { btcText, parseDecimal } from "../../utils/format";
import { dollarTransferFee, transferCurrency, transferDestinations } from "../../utils/transactionForm";

/**
 * The values the form fills in itself: a Deposit's or Withdrawal's currency
 * from its account (Bank is USD, Wallet BTC; the Exchange's is chosen), a
 * Transfer's destination from its source, and a Transfer's fee as what was
 * sent less what arrived (in dollars too, #447). A BTC transfer can also go
 * to its own account (a consolidation, #159): a destination the source
 * allows is kept, so an edit opens with the saved one; choosing another
 * source clears it (TransferFields), and the usual one is filled in.
 */
export function useFieldAutofill(type: TransactionType | "", form: UseFormReturn<TransactionFormData>) {
  const { watch, setValue } = form;
  const account = watch("account");
  const fromAccount = watch("fromAccount");
  const fromCurrency = watch("fromCurrency");
  const toAccount = watch("toAccount");
  const amountFrom = parseDecimal(watch("amountFrom")) || 0;
  const amountTo = parseDecimal(watch("amountTo")) || 0;

  useEffect(() => {
    if (type === "Deposit" || type === "Withdrawal") {
      if (account === "Bank") {
        setValue("currency", "USD");
      } else if (account === "Wallet") {
        setValue("currency", "BTC");
      }
    }
  }, [type, account, setValue]);

  useEffect(() => {
    if (type !== "Transfer") return;
    const currency = transferCurrency(fromAccount, fromCurrency);
    if (fromAccount !== "Exchange" && currency) setValue("fromCurrency", currency);
    const choices = transferDestinations(fromAccount, currency);
    if (choices.length === 0) return;
    if (!toAccount || !choices.includes(toAccount)) setValue("toAccount", choices[0]);
    setValue("toCurrency", currency);
  }, [type, fromAccount, fromCurrency, toAccount, setValue]);

  useEffect(() => {
    if (type !== "Transfer") return;
    if (fromCurrency === "BTC") {
      const fee = amountFrom - amountTo;
      setValue("fee", fee < 0 ? 0 : btcText(fee)); // "0.00000014", never "1.4e-7" (#101)
    } else if (fromCurrency === "USD") {
      setValue("fee", Math.max(dollarTransferFee(amountFrom, amountTo), 0)); // the one the save sends (#447)
    }
  }, [type, fromCurrency, amountFrom, amountTo, setValue]);
}
