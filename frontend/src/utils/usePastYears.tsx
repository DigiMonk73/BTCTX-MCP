// A write through the past-year warning (spec 5.8), for any screen that makes
// one: the 409 opens the dialog, and Save anyway sends the same write again
// with the 409's fingerprint (a new 409, for a ledger that changed meanwhile,
// asks again).
import React, { useCallback, useState } from "react";
import PastYearsDialog from "../components/PastYearsDialog";
import {
  addsSkipAsking,
  pastYearsWarning,
  stopAskingForAdds,
  type PastYearsWarning,
} from "./pastYears";

export interface PastYears {
  through: <T>(send: (confirm?: string) => Promise<T>, forAdd: boolean) => Promise<T | null>;
  dialog: React.ReactNode;
}

export function usePastYears(): PastYears {
  const [asking, setAsking] = useState<{
    warning: PastYearsWarning;
    forAdd: boolean;
    answer: (stopAsking: boolean | null) => void;
  } | null>(null);

  const ask = useCallback((warning: PastYearsWarning, forAdd: boolean): Promise<boolean | null> => {
    return new Promise((resolve) => {
      setAsking({
        warning,
        forAdd,
        answer: (stopAsking) => {
          setAsking(null);
          resolve(stopAsking);
        },
      });
    });
  }, []);

  const through = useCallback(async <T,>(
    send: (confirm?: string) => Promise<T>,
    forAdd: boolean,
  ): Promise<T | null> => {
    let confirm: string | undefined;
    for (;;) {
      try {
        return await send(confirm);
      } catch (error: unknown) {
        const warning = pastYearsWarning(error);
        if (warning === null) throw error;
        const quietAdd = forAdd && addsSkipAsking(warning.years) && warning.confirm !== confirm;
        if (!quietAdd) {
          const stopAsking = await ask(warning, forAdd);
          if (stopAsking === null) return null;
          if (stopAsking) stopAskingForAdds(warning.years);
        }
        // Sent blind never: each add still gets its own 409 and its own fingerprint
        confirm = warning.confirm;
      }
    }
  }, [ask]);

  const dialog = asking && (
    <PastYearsDialog
      warning={asking.warning}
      forAdd={asking.forAdd}
      onSave={(s) => asking.answer(s)}
      onCancel={() => asking.answer(null)}
    />
  );

  return { through, dialog };
}
