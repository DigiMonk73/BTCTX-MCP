// The words the app shows about what BitcoinTX is and isn't, worded as in the
// README, the landing page and the PDFs (the owner's decision, 2026-10-10).

/** The standard short disclaimer. */
export const DISCLAIMER =
  "BitcoinTX is software, not tax, legal or financial advice. It works from the records you enter: " +
  "check its figures with a tax professional before you file.";

/** The notice on wallets and exchanges, after its bold "Important: add each wallet and exchange.", with
 * 5.14's one wording of the IRS rule, the full wording of BitcoinTX's method (decision 30, #713) and Q5's
 * note for a ledger kept together in 1.x (2.0 spec 5.9, Q20) */
export const ACCOUNTS_NOTICE =
  "Add each wallet, exchange and bank you use in Settings, under Wallets, exchanges and banks. From 2025, " +
  "cost basis is figured wallet by wallet and account by account; unless you identify the coins you sell, " +
  "first in, first out within each, by the date first acquired (Treas. Reg. §1.1012-1(j)). Cost basis is " +
  "per-wallet FIFO: each wallet and exchange uses its own oldest coins first for a sale, spend or transfer. If " +
  "you kept multiple wallets or exchanges together in BitcoinTX 1.x, years before you added them were figured " +
  "together: ask a tax professional whether an earlier return needs a change.";

/** The light hint next to a wallet's choice. */
export const WALLET_HINT = "A wallet is one set of keys: add each one you use in Settings → Wallets, exchanges and banks.";
