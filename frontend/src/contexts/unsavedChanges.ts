import { createContext } from "react";

/**
 * Where a page says whether it holds changes not yet saved (the transaction
 * panel), to the layout around it: Logout then leaves the asking to that
 * page's "Discard changes?" instead of asking too (#536).
 */
export const ReportUnsavedChanges = createContext<(unsaved: boolean) => void>(() => undefined);
