import React, { useLayoutEffect } from "react";
import { useFormContext, type FieldPath } from "react-hook-form";
import { accountName, byKind, chosenId, yours } from "../../utils/accounts";

interface AccountPickerProps {
  /** The element's id: its label and the e2e tests find the field by it. */
  id: string;
  label: string;
  field: "fromAccountId" | "toAccountId";
  book: AccountBook;
  /** The accounts that fit, given the row's own saved account (offered even when hidden). */
  choices: (savedId: number | undefined) => number[];
  /** The blank option's text. */
  placeholder: string;
  /** The error when none, or none that fits, is chosen. */
  requiredMessage: string;
  /** How an option reads; its name by default. */
  optionLabel?: (id: number) => string;
  /** Fields checked again when this one changes (a Transfer's amounts). */
  deps?: FieldPath<TransactionFormData>[];
  /** Not shown while it holds the only account that fits (a Buy's exchange
   * with one exchange: 1.x's form has no such field). */
  quietWhenFixed?: boolean;
  /** Hints under the field. */
  children?: React.ReactNode;
}

/**
 * One of the row's accounts, by id (2.0 spec 5.13): blank and required
 * while more than one fits, filled and read-only when exactly one does. A
 * saved account the book lacks is named "account N (missing)" and its
 * picker shows blank, so a save can't put the row into the first account.
 */
const AccountPicker: React.FC<AccountPickerProps> = ({
  id, label, field, book, choices, placeholder, requiredMessage, optionLabel, deps, quietWhenFixed, children,
}) => {
  const { register, watch, setValue, clearErrors, formState: { errors, defaultValues } } =
    useFormContext<TransactionFormData>();
  // Through chosenId: a blank select's "" is no account
  const chosen = chosenId(watch(field));
  const options = choices(chosenId(defaultValues?.[field]));
  const nameOf = optionLabel ?? ((account: number) => accountName(book, account));
  // One of the owner's accounts; a saved id the book lacks is kept, and refused
  const known = chosen !== undefined && yours(book).includes(chosen);
  // After every render, before the page is painted (so no select flashes
  // first), each idempotent: an account the other fields no longer allow
  // goes, and the only one that fits comes, its error with it. With nothing
  // allowed yet (the field it depends on blank or missing), the row's own
  // stays for when it is. Otherwise the select shows what the form holds:
  // blank for a saved id the book lacks, without writing the form, so the
  // id stays and the check below refuses it.
  useLayoutEffect(() => {
    if (known && chosen !== undefined && options.length > 0 && !options.includes(chosen)) {
      setValue(field, undefined);
    } else if (chosen === undefined && options.length === 1) {
      setValue(field, options[0]);
      clearErrors(field);
    } else {
      const element = document.getElementById(id);
      const showing = chosen !== undefined && options.includes(chosen) ? String(chosen) : "";
      // A value no option has selects none at all (value reads ""): the blank one is chosen instead
      if (element instanceof HTMLSelectElement && (element.value !== showing || element.selectedIndex < 0)) {
        element.value = showing;
      }
    }
  });
  const rules = {
    setValueAs: chosenId,
    validate: (value: number | undefined) => (value !== undefined && options.includes(value)) || requiredMessage,
    deps,
  };
  const fixed = options.length === 1 && chosen === options[0];
  if (fixed && quietWhenFixed) return <input type="hidden" {...register(field, rules)} />;
  const groups = byKind(book, options);
  const optionsOf = (ids: number[]) => ids.map((account) => (
    <option key={account} value={account}>{nameOf(account)}</option>
  ));
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      {fixed ? (
        <>
          <input id={id} type="text" className="input" value={nameOf(options[0])} readOnly />
          <input type="hidden" {...register(field, rules)} />
        </>
      ) : (
        <select id={id} className="input" {...register(field, rules)}>
          <option value="">{placeholder}</option>
          {groups
            ? groups.map((group) => <optgroup key={group.label} label={group.label}>{optionsOf(group.ids)}</optgroup>)
            : optionsOf(options)}
        </select>
      )}
      {chosen !== undefined && !known && <small className="field-hint">{accountName(book, chosen)}</small>}
      {errors[field] && <span className="field-error">{errors[field]?.message}</span>}
      {children}
    </div>
  );
};

export default AccountPicker;
