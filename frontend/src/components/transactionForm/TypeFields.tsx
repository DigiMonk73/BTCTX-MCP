import React from "react";
import BuyFields from "./BuyFields";
import DepositFields from "./DepositFields";
import SellFields from "./SellFields";
import TransferFields from "./TransferFields";
import WithdrawalFields from "./WithdrawalFields";

/** The fields of the chosen transaction type; none before one is chosen.
 * `transactionId`: the saved row being edited, if any. */
const TypeFields: React.FC<{ type: TransactionType | ""; book: AccountBook; transactionId?: number | null }> = ({
  type, book, transactionId,
}) => {
  switch (type) {
    case "Deposit":
      return <DepositFields book={book} />;
    case "Withdrawal":
      return <WithdrawalFields book={book} />;
    case "Transfer":
      return <TransferFields book={book} transactionId={transactionId} />;
    case "Buy":
      return <BuyFields book={book} />;
    case "Sell":
      return <SellFields book={book} />;
    default:
      return null;
  }
};

export default TypeFields;
