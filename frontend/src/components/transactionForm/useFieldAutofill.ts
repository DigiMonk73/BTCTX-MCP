import { useEffect } from "react";
import type { UseFormReturn } from "react-hook-form";
import { transferCurrency, transferDestinations } from "../../utils/transactionForm";

/**
 * The values the form fills in itself: a Deposit's or Withdrawal's currency
 * from its account (Bank is USD, Wallet BTC; the Exchange's is chosen), a
 * Transfer's destination from its source, and a BTC transfer's fee as what
 * was sent less what arrived. A BTC transfer can also go to its own account
 * (a consolidation, #159): a destination the source allows is kept, so an
 * edit opens with the saved one; choosing another source clears it
 * (TransferFields), and the usual one is filled in.
 */
export function useFieldAutofill(type: TransactionType | "", form: UseFormReturn<TransactionFormData>) {
  const { watch, setValue } = form;
  const account = watch("account");
  const fromAccount = watch("fromAccount");
  const fromCurrency = watch("fromCurrency");
  const toAccount = watch("toAccount");
  const amountFrom = watch("amountFrom") || 0;
  const amountTo = watch("amountTo") || 0;

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
    if (type === "Transfer" && fromCurrency === "BTC") {
      const fee = amountFrom - amountTo;
      setValue("fee", fee < 0 ? 0 : Number(fee.toFixed(8)));
    }
  }, [type, fromCurrency, amountFrom, amountTo, setValue]);
}
