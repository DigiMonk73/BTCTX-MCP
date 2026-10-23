import React from "react";
import { ALL_ACCOUNTS, filterGroups, type AccountChoice } from "../../utils/accountFilter";

interface AccountFilterProps {
  book: AccountBook;
  value: AccountChoice;
  onChange: (choice: AccountChoice) => void;
}

/** The Transactions page's account filter (P7's mockups, #356): a native
 * select with its choices grouped by kind, so a phone shows its own picker. */
const AccountFilter: React.FC<AccountFilterProps> = ({ book, value, onChange }) => (
  <select
    className="input select-pill"
    aria-label="Account"
    value={value}
    onChange={(e) => onChange(e.target.value)}
  >
    <option value={ALL_ACCOUNTS}>All accounts</option>
    {filterGroups(book).map((group) => (
      <optgroup key={group.label} label={group.label}>
        {group.options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </optgroup>
    ))}
  </select>
);

export default AccountFilter;
