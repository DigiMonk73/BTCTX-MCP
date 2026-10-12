import React from "react";
import { useFormContext } from "react-hook-form";
import { valueOrigin } from "../../utils/priceUsed";

type Key = keyof TransactionFormData;

/** Under a value BitcoinTX can fill in: "From the price: …" or "Typed" (#145, plan 2.5). */
const ValueOrigin: React.FC<{ fromPrice: Key; stored: Key; shown: Key }> = ({ fromPrice, stored, shown }) => {
  const { watch } = useFormContext<TransactionFormData>();
  const note = valueOrigin(
    watch(fromPrice) as boolean | undefined,
    watch(stored) as number | undefined,
    watch(shown) as number | undefined,
    watch("priceUsed") as PriceUsed | null | undefined,
  );
  return note ? <small className="field-hint field-origin">{note}</small> : null;
};

export default ValueOrigin;
