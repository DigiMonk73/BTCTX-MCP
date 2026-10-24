import React, { useState } from "react";
import { OPEN_CARDS_KEY, kindCards, openCardsAfter, readOpenCards, type CardKind } from "../../utils/dashboard";
import AccountCard from "./AccountCard";

// The browser may keep nothing (a private window, storage turned off): the
// cards then open closed each time, and nothing else changes
function storedOpenCards(): CardKind[] {
  try {
    return readOpenCards(window.localStorage.getItem(OPEN_CARDS_KEY));
  } catch {
    return [];
  }
}

function storeOpenCards(open: CardKind[]): void {
  try {
    window.localStorage.setItem(OPEN_CARDS_KEY, JSON.stringify(open));
  } catch {
    // Not kept: see storedOpenCards
  }
}

/** Bank, Exchange and Wallet, each with its total and its accounts (2.0
 * spec 5.13, P7's mockups); the cards left open are remembered in this
 * browser. */
const AccountCards: React.FC<{ balances: AccountBalance[] }> = ({ balances }) => {
  const [open, setOpen] = useState<CardKind[]>(storedOpenCards);
  const toggle = (kind: CardKind) => {
    const next = openCardsAfter(open, kind);
    setOpen(next);
    storeOpenCards(next);
  };
  return (
    <div className="account-cards" role="group" aria-label="Your accounts">
      {kindCards(balances).map((card) => (
        <AccountCard key={card.kind} card={card} open={open.includes(card.kind)} onToggle={() => toggle(card.kind)} />
      ))}
    </div>
  );
};

export default AccountCards;
