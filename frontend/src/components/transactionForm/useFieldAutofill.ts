import { useEffect } from "react";
import type { UseFormReturn } from "react-hook-form";

/**
 * The values the form fills in itself: a Deposit's or Withdrawal's currency
 * from its account (Bank is USD, Wallet BTC; the Exchange's is chosen), a
 * Transfer's destination from its source, and a BTC transfer's fee as what
 * was sent less what arrived.
 */
export function useFieldAutofill(type: TransactionType | "", form: UseFormReturn<TransactionFormData>) {
  const { watch, setValue } = form;
  const account = watch("account");
  const fromAccount = watch("fromAccount");
  const fromCurrency = watch("fromCurrency");
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
    if (type === "Transfer") {
      if (fromAccount === "Bank") {
        setValue("fromCurrency", "USD");
        setValue("toAccount", "Exchange");
        setValue("toCurrency", "USD");
      } else if (fromAccount === "Wallet") {
        setValue("fromCurrency", "BTC");
        setValue("toAccount", "Exchange");
        setValue("toCurrency", "BTC");
      } else if (fromAccount === "Exchange") {
        if (fromCurrency === "USD") {
          setValue("toAccount", "Bank");
          setValue("toCurrency", "USD");
        } else if (fromCurrency === "BTC") {
          setValue("toAccount", "Wallet");
          setValue("toCurrency", "BTC");
        }
      }
    }
  }, [type, fromAccount, fromCurrency, setValue]);

  useEffect(() => {
    if (type === "Transfer" && fromCurrency === "BTC") {
      const fee = amountFrom - amountTo;
      setValue("fee", fee < 0 ? 0 : Number(fee.toFixed(8)));
    }
  }, [type, fromCurrency, amountFrom, amountTo, setValue]);
}
