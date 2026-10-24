import { useEffect } from "react";
import type { UseFormReturn } from "react-hook-form";
import { accountCurrency, chosenId } from "../../utils/accounts";
import { btcText, parseDecimal } from "../../utils/format";
import { dollarTransferFee } from "../../utils/transferAmounts";

/**
 * The value the form fills in itself: a Transfer's fee, what was sent less
 * what arrived, in its From's currency (in dollars too, #447). The accounts
 * fill themselves only where exactly one fits (AccountPicker, 5.13). The
 * effect depends on the currency's text, never the book, so a new book
 * object can't run it again.
 */
export function useFieldAutofill(type: TransactionType | "", form: UseFormReturn<TransactionFormData>, book?: AccountBook) {
  const { watch, setValue } = form;
  const fromCurrency = book ? accountCurrency(book, chosenId(watch("fromAccountId"))) : undefined;
  const amountFrom = parseDecimal(watch("amountFrom")) || 0;
  const amountTo = parseDecimal(watch("amountTo")) || 0;

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
