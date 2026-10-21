import React, { useEffect } from "react";
import { useFormContext, type FieldPath } from "react-hook-form";
import { accountName, yours } from "../../utils/accounts";

interface AccountPickerProps {
  /** The element's id: labels and the e2e tests find the field by it. */
  id: string;
  label: string;
  field: "fromAccountId" | "toAccountId";
  book: AccountBook;
  /** The accounts that fit, given the row's own saved account (offered even when hidden). */
  choices: (savedId: number | undefined) => number[];
  /** The blank option's text. */
  placeholder: string;
  /** The error when none (or none that fits) is chosen. */
  requiredMessage: string;
  /** How an option reads; the nickname by default. */
  optionLabel?: (id: number) => string;
  /** Fields checked again when this one changes (a Transfer's amounts). */
  deps?: FieldPath<TransactionFormData>[];
  /** Hints under the field. */
  children?: React.ReactNode;
}

/** A select's "" is no account; anything else is an id. */
function chosenId(value: unknown): number | undefined {
  return value === "" || value == null ? undefined : Number(value);
}

const AccountPicker: React.FC<AccountPickerProps> = ({
  id,
  label,
  field,
  book,
  choices,
  placeholder,
  requiredMessage,
  optionLabel,
  deps,
  children,
}) => {
  const { register, watch, setValue, formState: { errors, defaultValues } } = useFormContext<TransactionFormData>();
  // A blank select is "" in the form until setValueAs runs, and "" is not
  // "no account": without chosenId the only fitting account would never fill,
  // and a new row would show a missing-account hint (5.13).
  const chosen = chosenId(watch(field));
  const options = choices(defaultValues?.[field]);
  const nameOf = optionLabel ?? ((account: number) => accountName(book, account));
  // One of the owner's accounts; a saved id the book lacks is "missing" and is kept (D3)
  const known = chosen !== undefined && yours(book).includes(chosen);
  // After every render, both idempotent: an account the other fields no longer allow
  // goes, and the only one that fits comes (5.13: "filled only when exactly one fits").
  // A saved id the book lacks matches no option, so nothing is selected and the
  // field reads as undefined. Select the blank option without writing the form:
  // the id stays, the field shows empty, and the check refuses it (D3).
  useEffect(() => {
    if (known && chosen !== undefined && !options.includes(chosen)) setValue(field, undefined);
    else if (chosen === undefined && options.length === 1) setValue(field, options[0]);
    else if (chosen !== undefined && !options.includes(chosen)) {
      const element = document.getElementById(id);
      if (element instanceof HTMLSelectElement && element.selectedIndex !== 0) element.value = "";
    }
  });
  const rules = {
    setValueAs: chosenId,
    validate: (value: number | undefined) => (value !== undefined && options.includes(value)) || requiredMessage,
    deps,
  };
  const fixed = options.length === 1 && chosen === options[0];
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      {fixed ? (
        <>
          <input id={id} type="text" className="input" value={nameOf(chosen)} readOnly />
          <input type="hidden" {...register(field, rules)} />
        </>
      ) : (
        <select id={id} className="input" {...register(field, rules)}>
          <option value="">{placeholder}</option>
          {options.map((account) => (
            <option key={account} value={account}>{nameOf(account)}</option>
          ))}
        </select>
      )}
      {chosen !== undefined && !known && <small className="field-hint">{accountName(book, chosen)}</small>}
      {errors[field] && <span className="field-error">{errors[field]?.message}</span>}
      {children}
    </div>
  );
};

export default AccountPicker;
