// Matching another exchange's columns (B5b, #567): the owner's own mapping
// as the column matcher edits it, and the mapping it sends. A mapping says
// how to read a file, never where its rows go: the exchange and the wallet
// are chosen for each file.

/** The exchange file chosen when the owner matches another exchange's columns. */
export const MATCH_COLUMNS = "match";

export type Role = "date" | "time" | "kind" | "btc" | "usd" | "fee" | "fee_currency" | "fee_btc" | "asset"
  | "status" | "row_id";

export interface RoleInfo {
  role: Role;
  label: string;
  hint: string;
  required: boolean;
}

/** Each column the matcher asks for, in the order it shows them. */
export const ROLES: RoleInfo[] = [
  { role: "date", label: "Date", hint: "When it happened, with its time.", required: true },
  { role: "time", label: "Time", hint: "Only if the time is in a column of its own.", required: false },
  { role: "kind", label: "Kind of row", hint: "Buy, sell, send…: you say what each word means below.", required: true },
  { role: "btc", label: "Bitcoin amount", hint: "The bitcoin bought, sold, sent or received.", required: true },
  { role: "usd", label: "Dollar amount", hint: "What a buy cost or a sell brought.", required: false },
  { role: "fee", label: "Fee", hint: "In dollars, unless its cell (0.0001 BTC) or a column says its currency.", required: false },
  { role: "fee_currency", label: "Fee currency", hint: "Only if a column says each fee's currency (USD, BTC).", required: false },
  { role: "fee_btc", label: "Network fee in bitcoin", hint: "A send's fee, if it has a column of its own.", required: false },
  { role: "asset", label: "Asset", hint: "Only if the file has other coins: their rows are left out.", required: false },
  { role: "status", label: "Status", hint: "Only if some rows didn't complete: they're left out.", required: false },
  { role: "row_id", label: "Row id", hint: "The exchange's own id: a row repeated in the file is left out.", required: false },
];

/** What each kind means, as the matcher's choices say it. */
export const KIND_CHOICES: { kind: MappingKind; label: string }[] = [
  { kind: "buy", label: "Buy" },
  { kind: "sell", label: "Sell" },
  { kind: "send", label: "Send out" },
  { kind: "receive", label: "Receive in" },
  { kind: "income", label: "Income" },
  { kind: "interest", label: "Interest" },
  { kind: "reward", label: "Reward (staking, mining, bonus)" },
  { kind: "rebate", label: "Rebate (cash-back)" },
  { kind: "leave out", label: "Leave out" },
];

/** The matcher's state: a mapping being made or edited. */
export interface Draft {
  name: string;
  columns: Partial<Record<Role, string>>;
  kinds: Record<string, MappingKind | "">;
  zone: string;
  buyAfterFee: boolean;
  sellAfterFee: boolean;
  sendFeeIncluded: boolean;
  decimalComma: boolean;
  dayFirst: boolean;
  btcAssets: string[];
  done: string[];
}

export function emptyDraft(): Draft {
  return {
    name: "", columns: {}, kinds: {}, zone: "UTC", buyAfterFee: false, sellAfterFee: false,
    sendFeeIncluded: false, decimalComma: false, dayFirst: false, btcAssets: ["BTC"], done: [],
  };
}

// A column's usual names (lowercase), by the role they hold
const USUAL_NAMES: Record<Role, string[]> = {
  date: ["date", "timestamp", "datetime", "date (utc)", "time (utc)", "date & time (utc)", "created at"],
  time: [],
  kind: ["type", "transaction type", "kind", "event", "tag"],
  btc: ["btc", "amount btc", "btc amount", "amount (btc)", "quantity", "quantity transacted", "asset amount",
    "bitcoin amount", "unit count"],
  usd: ["usd", "amount usd", "usd amount", "amount (usd)", "subtotal"],
  fee: ["fee", "fees", "fee usd", "fee amount"],
  fee_currency: ["fee currency"],
  fee_btc: ["fee btc", "network fee btc"],
  asset: ["asset", "asset type", "coin"],
  status: ["status", "state"],
  row_id: ["id", "transaction id", "reference", "ref", "txid"],
};

/** The columns whose names say what they hold: a guess the owner checks,
 * each column for one role at most. */
export function guessColumns(columns: string[]): Partial<Record<Role, string>> {
  const taken = new Set<string>();
  const found: Partial<Record<Role, string>> = {};
  for (const { role } of ROLES) {
    const column = columns.find((c) => !taken.has(c) && USUAL_NAMES[role].includes(c.trim().toLowerCase()));
    if (column !== undefined) {
      found[role] = column;
      taken.add(column);
    }
  }
  return found;
}

// The words that can mean only one thing; anything else (a deposit of
// dollars or of bitcoin?) is the owner's to say
const PLAIN_WORDS: Record<string, MappingKind> = {
  buy: "buy", bought: "buy", purchase: "buy", purchased: "buy", sell: "sell", sold: "sell", sale: "sell",
};

export function guessKinds(words: string[]): Record<string, MappingKind> {
  const found: Record<string, MappingKind> = {};
  for (const word of words) {
    const kind = PLAIN_WORDS[word.trim().toLowerCase()];
    if (kind) found[word] = kind;
  }
  return found;
}

/** The mapping the draft says: the columns chosen, the words given a kind. */
export function mappingFrom(draft: Draft): OwnMapping {
  const columns = Object.fromEntries(Object.entries(draft.columns).filter(([, name]) => name)) as unknown as OwnColumns;
  const kinds = Object.fromEntries(Object.entries(draft.kinds).filter(([, kind]) => kind)) as Record<string, MappingKind>;
  const afterFee: ("buy" | "sell")[] = [];
  if (draft.buyAfterFee) afterFee.push("buy");
  if (draft.sellAfterFee) afterFee.push("sell");
  return {
    name: draft.name.trim(),
    columns,
    kinds,
    zone: draft.zone,
    dollars_after_fee: afterFee,
    send_fee_included: draft.sendFeeIncluded,
    decimal_comma: draft.decimalComma,
    day_first: draft.dayFirst,
    btc_assets: draft.btcAssets,
    done: draft.done,
  };
}

/** A saved mapping, to edit. */
export function draftFrom(mapping: OwnMapping): Draft {
  return {
    name: mapping.name,
    columns: { ...mapping.columns },
    kinds: { ...mapping.kinds },
    zone: mapping.zone,
    buyAfterFee: mapping.dollars_after_fee.includes("buy"),
    sellAfterFee: mapping.dollars_after_fee.includes("sell"),
    sendFeeIncluded: mapping.send_fee_included,
    decimalComma: mapping.decimal_comma,
    dayFirst: mapping.day_first,
    btcAssets: [...mapping.btc_assets],
    done: [...mapping.done],
  };
}

/** What the draft still needs before it can read a file: the columns
 * required, then a word read as a kind. */
export function missingRoles(draft: Draft): { role: Role | "kinds"; label: string }[] {
  const missing: { role: Role | "kinds"; label: string }[] = ROLES
    .filter((r) => r.required && !draft.columns[r.role])
    .map((r) => ({ role: r.role, label: r.label }));
  if (missing.length === 0 && !Object.values(draft.kinds).some(Boolean)) {
    missing.push({ role: "kinds", label: "What each kind of row is" });
  }
  return missing;
}

/** The zones a file's times can be in: UTC, "each date says its own", this
 * browser's, then every zone the browser knows (none on an older Safari). */
export function fileZones(): string[] {
  const intl = Intl as unknown as { supportedValuesOf?: (key: string) => string[] };
  const all = intl.supportedValuesOf ? intl.supportedValuesOf("timeZone") : [];
  return Array.from(new Set(["UTC", "dates", Intl.DateTimeFormat().resolvedOptions().timeZone, ...all]));
}
