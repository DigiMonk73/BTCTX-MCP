import React, { useLayoutEffect } from "react";
import { useFormContext, type FieldPath, type UseFormRegisterReturn } from "react-hook-form";
import { accountName, byKind, chosenId, yours } from "../../utils/accounts";

type PickerField = "fromAccountId" | "toAccountId";

interface AccountPickerProps {
  /** The element's id: its label and the e2e tests find the field by it. */
  id: string;
  label: string;
  field: PickerField;
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
  /** What else a choice here changes (a Transfer's From, its To). */
  onChange?: () => void;
  /** Whether an account may be filled in as the only one that fits; else it
   * must be chosen (a Transfer's From itself: a consolidation). */
  fillable?: (id: number) => boolean;
  /** Not shown while it holds the only account that fits (a Buy's exchange
   * with one exchange: 1.x's form has no such field). */
  quietWhenFixed?: boolean;
  /** Hints under the field. */
  children?: React.ReactNode;
}

/**
 * Keeps a picker's account in step, after every render and before the page
 * is painted (so no select flashes first), each step idempotent: an account
 * the other fields no longer allow goes, and the only one that may be filled
 * in comes, its error with it. With nothing allowed yet (the field it
 * depends on blank or missing), the row's own stays for when it is.
 * Otherwise the select shows what the form holds: blank for a saved id the
 * book lacks, without writing the form, so the id stays and the check refuses it.
 */
function useAccountInStep(
  { id, field, book, choices, fillable }: Pick<AccountPickerProps, "id" | "field" | "book" | "choices" | "fillable">,
) {
  const { watch, setValue, clearErrors, formState: { defaultValues } } = useFormContext<TransactionFormData>();
  // Through chosenId: a blank select's "" is no account
  const chosen = chosenId(watch(field));
  const options = choices(chosenId(defaultValues?.[field]));
  // One of the owner's accounts; a saved id the book lacks is kept, and refused
  const known = chosen !== undefined && yours(book).includes(chosen);
  const only = options.length === 1 && (fillable?.(options[0]) ?? true) ? options[0] : undefined;
  useLayoutEffect(() => {
    if (known && chosen !== undefined && options.length > 0 && !options.includes(chosen)) {
      setValue(field, undefined);
    } else if (chosen === undefined && only !== undefined) {
      setValue(field, only);
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
  return { chosen, options, known, only };
}

/** The accounts that fit, after a blank first option; grouped by kind once there's more than one of a kind (P7). */
const AccountSelect: React.FC<{
  id: string;
  placeholder: string;
  options: number[];
  book: AccountBook;
  nameOf: (id: number) => string;
  registered: UseFormRegisterReturn;
}> = ({ id, placeholder, options, book, nameOf, registered }) => {
  const groups = byKind(book, options);
  const optionsOf = (ids: number[]) => ids.map((account) => (
    <option key={account} value={account}>{nameOf(account)}</option>
  ));
  return (
    <select id={id} className="input" {...registered}>
      <option value="">{placeholder}</option>
      {groups
        ? groups.map((group) => <optgroup key={group.label} label={group.label}>{optionsOf(group.ids)}</optgroup>)
        : optionsOf(options)}
    </select>
  );
};

/**
 * One of the row's accounts, by id (2.0 spec 5.13): blank and required
 * while more than one fits, filled and read-only when exactly one does and
 * may be filled in (`fillable`: never a Transfer's From itself). A
 * saved account the book lacks is named "account N (missing)" and its
 * picker shows blank, so a save can't put the row into the first account.
 */
const AccountPicker: React.FC<AccountPickerProps> = ({
  id, label, field, book, choices, placeholder, requiredMessage, optionLabel, deps, onChange, fillable, quietWhenFixed,
  children,
}) => {
  const { register, formState: { errors } } = useFormContext<TransactionFormData>();
  const { chosen, options, known, only } = useAccountInStep({ id, field, book, choices, fillable });
  const nameOf = optionLabel ?? ((account: number) => accountName(book, account));
  const rules = {
    setValueAs: chosenId,
    validate: (value: number | undefined) => (value !== undefined && options.includes(value)) || requiredMessage,
    deps,
    onChange,
  };
  const fixed = only !== undefined && chosen === only;
  if (fixed && quietWhenFixed) return <input type="hidden" {...register(field, rules)} />;
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      {fixed ? (
        <>
          <input id={id} type="text" className="input" value={nameOf(options[0])} readOnly />
          <input type="hidden" {...register(field, rules)} />
        </>
      ) : (
        <AccountSelect
          id={id} placeholder={placeholder} options={options} book={book} nameOf={nameOf}
          registered={register(field, rules)}
        />
      )}
      {chosen !== undefined && !known && <small className="field-hint">{accountName(book, chosen)}</small>}
      {errors[field] && <span className="field-error">{errors[field]?.message}</span>}
      {children}
    </div>
  );
};

export default AccountPicker;
