// Where a transfer can go and in which currency, as the form offers it;
// kept apart from the form's mapping (transactionForm.ts), which doesn't use them.

/** A transfer's currency: Bank's is USD, Wallet's BTC; the Exchange's is chosen. */
export function transferCurrency(account?: AccountType, currency?: Currency): Currency | undefined {
  if (account === "Bank") return "USD";
  if (account === "Wallet") return "BTC";
  return account === "Exchange" ? currency : undefined;
}

/**
 * Where a Transfer from an account (in a currency) can go, the usual place
 * first: the other account of that currency, or for a BTC account itself too
 * (a consolidation, or a move between wallets BitcoinTX pools: only the fee
 * is recorded, #159).
 */
export function transferDestinations(account?: AccountType, currency?: Currency): AccountType[] {
  switch (`${account}/${transferCurrency(account, currency)}`) {
    case "Bank/USD":
      return ["Exchange"];
    case "Wallet/BTC":
      return ["Exchange", "Wallet"];
    case "Exchange/USD":
      return ["Bank"];
    case "Exchange/BTC":
      return ["Wallet", "Exchange"];
    default:
      return [];
  }
}
