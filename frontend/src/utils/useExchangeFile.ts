// The exchange file the import reads (B5b, #567): its mapping (River's,
// another ready-made one, the owner's own, or another exchange's being
// matched), the columns read from the file for the matcher, and the routes
// its preview and import go to. River's file keeps River's own routes, as
// before; every other goes to the exchange routes, an unsaved or edited
// mapping sent as it is drafted.
import { useCallback, useEffect, useRef, useState } from "react";
import api from "../api";
import { detailOr } from "./apiError";
import {
  MATCH_COLUMNS, draftFrom, emptyDraft, guessColumns, guessKinds, mappingFrom, missingRoles, type Draft,
} from "./exchangeMapping";

interface Toasts {
  error: (message: string) => void;
  success: (message: string) => void;
}

const RIVER_URLS = { preview: "/import/river/preview", execute: "/import/river/execute" };
const EXCHANGE_URLS = { preview: "/import/exchange/preview", execute: "/import/exchange/execute" };
// What a mapping not yet named is called in the preview's messages ("… this exchange's file")
const UNNAMED = "this exchange";

/** A draft for a file's columns: what their names say, the plain words of its kind column. */
function guessed(file: FileColumnsResponse): Draft {
  const columns = guessColumns(file.columns);
  return { ...emptyDraft(), columns, kinds: guessKinds(columns.kind ? file.values[columns.kind] ?? [] : []) };
}

/** Whether every column the draft names is one of the file's: another export of the same exchange. */
function fits(draft: Draft, file: FileColumnsResponse): boolean {
  const named = Object.values(draft.columns).filter(Boolean);
  return named.length > 0 && named.every((name) => file.columns.includes(name as string));
}

export function useExchangeFile(toast: Toasts) {
  const [mappings, setMappings] = useState<ExchangeMapping[] | undefined>();
  const [chosenId, setChosenId] = useState("river");
  const [columns, setColumns] = useState<FileColumnsResponse | null>(null);
  const [draft, setDraft] = useState<Draft>(emptyDraft());
  // The choice the draft was made for: another exchange's matching is kept for a file like the last
  const [draftOf, setDraftOf] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  // The latest file whose columns were asked for: an earlier one's late answer is dropped
  const asked = useRef(0);

  const reload = useCallback(async () => {
    try {
      setMappings((await api.get<MappingsResponse>("/import/exchange/mappings")).data.mappings);
    } catch {
      setMappings(undefined); // River alone, as before, until the list can be read
    }
  }, []);
  useEffect(() => { void reload(); }, [reload]);

  const listed = (id: string) => mappings?.find((m) => m.id === id);
  const matches = (id: string) => id === MATCH_COLUMNS || listed(id)?.ready_made === false;
  const chosen = listed(chosenId);
  const matching = matches(chosenId);

  /** The file's columns, for the matcher: the saved mapping's for one of the owner's; for another
   * exchange's, the matching so far when the file has its columns, else what their names say. */
  const readColumns = async (id: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    const mine = ++asked.current;
    try {
      const found = (await api.post<FileColumnsResponse>("/import/exchange/columns", form)).data;
      if (mine !== asked.current) return;
      setColumns(found);
      const own = listed(id)?.mapping;
      const kept = id === MATCH_COLUMNS && draftOf === MATCH_COLUMNS && fits(draft, found);
      if (!kept) setDraft(own ? draftFrom(own) : guessed(found));
      setDraftOf(id);
    } catch (err) {
      if (mine === asked.current) toast.error(detailOr(err, "Couldn't read the file's columns."));
    }
  };

  /** Another mapping for the file (with `file` chosen already, its columns are read for the matcher). */
  const choose = async (id: string, file: File | null) => {
    asked.current += 1; // an answer still on its way was for the choice before
    setChosenId(id);
    setColumns(null);
    if (matches(id) && file) await readColumns(id, file);
  };

  /** A new file: its columns are read again when its columns are being matched. */
  const fileChosen = async (file: File | null) => {
    asked.current += 1;
    setColumns(null);
    if (matching && file) await readColumns(chosenId, file);
  };

  /** The preview's form fields that say how to read the file. */
  const addMapping = (form: FormData) => {
    if (chosenId === "river") return; // River's own route
    if (!matching) {
      form.append("mapping_id", chosenId);
      return;
    }
    form.append("mapping", JSON.stringify(mappingFrom({ ...draft, name: draft.name.trim() || UNNAMED })));
  };

  /** Save the draft: a new mapping of the owner's, or the one being edited. */
  const save = async () => {
    setSaving(true);
    try {
      const own = mappingFrom(draft);
      const saved = chosenId === MATCH_COLUMNS
        ? (await api.post<ExchangeMapping>("/import/exchange/mappings", own)).data
        : (await api.put<ExchangeMapping>(`/import/exchange/mappings/${chosenId}`, own)).data;
      await reload();
      setChosenId(saved.id);
      setDraftOf(saved.id);
      toast.success(`Saved “${saved.name}”.`);
    } catch (err) {
      toast.error(detailOr(err, "Couldn't save the mapping."));
    } finally {
      setSaving(false);
    }
  };

  /** Delete the owner's mapping being edited; the matcher keeps its draft, to save again. */
  const remove = async () => {
    try {
      await api.delete(`/import/exchange/mappings/${chosenId}`);
      await reload();
      setChosenId(MATCH_COLUMNS);
      setDraftOf(MATCH_COLUMNS);
      toast.success(`Deleted “${chosen?.name ?? draft.name}”.`);
    } catch (err) {
      toast.error(detailOr(err, "Couldn't delete the mapping."));
    }
  };

  return {
    mappings, chosenId, chosen, matching, columns, draft, setDraft, saving,
    choose, fileChosen, addMapping, save, remove,
    name: chosenId === "river" ? "River" : chosen?.name ?? (draft.name.trim() || "Exchange"),
    urls: chosenId === "river" ? RIVER_URLS : EXCHANGE_URLS,
    // A matched file previews once its columns are read and say what each holds
    ready: !matching || (columns !== null && missingRoles(draft).length === 0),
  };
}

export type ExchangeFile = ReturnType<typeof useExchangeFile>;
