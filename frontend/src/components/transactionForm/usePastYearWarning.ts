// The past-year warning's round on the form (2.0 spec 5.8, #352): a save or
// delete the server answers with the warning is asked about, or for an add
// to years the owner keeps quiet confirmed by the page, then sent again with
// its confirm. A warning that comes back to a confirm (the ledger changed
// meanwhile) is asked about as it is now.
import { useCallback, useRef, useState, type RefObject } from "react";
import {
  addsQuietFor,
  keepAddsQuiet,
  pastYearWarning,
  type PastYearKind,
  type PastYearWarning,
  type WarnedAgain,
} from "../../utils/pastYears";

/** A request the form sends, with the confirm once there is one. */
export type ConfirmableRequest<T> = (confirm?: string) => Promise<T>;

/** What the dialog shows, and its answers. */
export interface PastYearQuestion {
  kind: PastYearKind;
  warning: PastYearWarning;
  /** Why it's asked again, if it is: the server refused a confirm, and `warning` is what it changes now. */
  changed: WarnedAgain | null;
  busy: boolean;
  opener: RefObject<HTMLElement | null>;
  onConfirm: (quiet: boolean) => void;
  onCancel: () => void;
}

/** The owner's answer: confirmed (with "Don't ask again" ticked or not), or cancelled. */
type Answer = { quiet: boolean } | null;

/** The warning in a failed request; any other failure goes on to the form's own handling. */
function warningIn(error: unknown): PastYearWarning {
  const warning = pastYearWarning(error);
  if (warning === null) throw error;
  return warning;
}

export function usePastYearWarning() {
  const [asked, setAsked] = useState<Pick<PastYearQuestion, "kind" | "warning" | "changed"> | null>(null);
  const [busy, setBusy] = useState(false);
  const answer = useRef<(choice: Answer) => void>(() => undefined);
  const opener = useRef<HTMLElement | null>(null);

  const ask = useCallback(
    (kind: PastYearKind, warning: PastYearWarning, changed: WarnedAgain | null) =>
      new Promise<Answer>((resolve) => {
        answer.current = resolve;
        setBusy(false);
        setAsked({ kind, warning, changed });
      }),
    [],
  );

  /** Asked until the owner cancels, or a confirmed request succeeds or fails otherwise. */
  const askUntilDone = useCallback(
    async <T>(kind: PastYearKind, first: PastYearWarning, send: ConfirmableRequest<T>,
      againFirst: WarnedAgain | null): Promise<T | null> => {
      let warning = first;
      let changed = againFirst;
      try {
        for (;;) {
          const choice = await ask(kind, warning, changed);
          if (choice === null) return null;
          setBusy(true);
          try {
            const result = await send(warning.confirm);
            // Only once the add is saved: a refused or failed confirm keeps no year quiet
            if (choice.quiet) keepAddsQuiet(warning.years);
            return result;
          } catch (error) {
            warning = warningIn(error);
            changed = "confirmed";
          }
        }
      } finally {
        setAsked(null);
        setBusy(false);
      }
    },
    [ask],
  );

  /**
   * `send`, through the warning: its result, or null when the owner
   * cancelled (nothing saved). Any other failure is thrown as it came.
   */
  const attempt = useCallback(
    async <T>(kind: PastYearKind, send: ConfirmableRequest<T>): Promise<T | null> => {
      // Taken now: by the time the dialog opens, the Save button is disabled
      opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      let warning: PastYearWarning;
      try {
        return await send();
      } catch (error) {
        warning = warningIn(error);
      }
      if (kind !== "add" || !addsQuietFor(warning.years)) return askUntilDone(kind, warning, send, null);
      try {
        return await send(warning.confirm);
      } catch (error) {
        return askUntilDone(kind, warningIn(error), send, "quiet");
      }
    },
    [askUntilDone],
  );

  const onConfirm = useCallback((quiet: boolean) => answer.current({ quiet }), []);
  const onCancel = useCallback(() => answer.current(null), []);
  const question: PastYearQuestion | null = asked && { ...asked, busy, opener, onConfirm, onCancel };
  return {
    attempt,
    question,
    /** The dialog waits for the owner: no request is running. */
    asking: asked !== null && !busy,
  };
}
