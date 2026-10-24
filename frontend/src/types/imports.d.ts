// The CSV and River imports' previews and results, as the server sends them.

declare global {
  // The CSV import's preview (POST /api/import/preview) and status.
  interface CSVRowPreview {
    row_number: number;
    date: string;
    type: string;
    amount: string;
    amount_currency: "BTC" | "USD";
    from_account: string;
    to_account: string;
    cost_basis_usd?: string;
    proceeds_usd?: string;
    fee_amount?: string;
    fee_currency?: string;
    source?: string;
    purpose?: string;
    notes?: string;
  }

  interface CSVParseError {
    row_number: number;
    column?: string;
    message: string;
    severity: string;
  }

  interface CSVPreviewResponse {
    success: boolean;
    total_rows: number;
    valid_rows: number;
    transactions: CSVRowPreview[];
    errors: CSVParseError[];
    warnings: CSVParseError[];
    can_import: boolean;
  }

  interface DatabaseStatusResponse {
    is_empty: boolean;
    transaction_count: number;
    message: string;
  }

  // River's bitcoin-activity CSV: the preview (POST /api/import/river/preview)
  // and the import. Row problems have the CSV import's shape.
  interface RiverProposal {
    row_number: number;
    date: string;
    river_tag?: string;
    type: string;
    from_account: string;
    to_account: string;
    amount: string;
    cost_basis_usd?: string;
    proceeds_usd?: string;
    fee_amount?: string;
    fee_currency?: string;
    source?: string;
    purpose?: string;
    type_choices: string[];
    funding_choices: string[];
    basis_autofilled: boolean;
    price_moment?: "hour" | "day" | null;
    status: "new" | "matched" | "discrepancy";
    matched_tx_id?: number;
    discrepancy?: string;
    near_amount?: boolean;
  }

  interface RiverPreviewResponse {
    success: boolean;
    total_rows: number;
    new_count: number;
    matched_count: number;
    discrepancy_count: number;
    proposals: RiverProposal[];
    errors: CSVParseError[];
    warnings: CSVParseError[];
    /** The tax years before this one the rows not in the ledger are dated
     * in: importing them can change those years' figures, so the import asks first */
    past_years_dated?: number[];
  }

  interface RiverImportResponse {
    success: boolean;
    imported_count: number;
    skipped_existing: number;
    message: string;
  }

  // The importer for any exchange's file (B5b, /api/import/exchange): its
  // preview and import are River's shapes above.
  type MappingKind = "buy" | "sell" | "send" | "receive" | "income" | "interest" | "reward" | "rebate"
    | "dollars" | "convert" | "leave out";

  interface OwnColumns {
    date: string;
    kind: string;
    btc: string;
    time?: string;
    usd?: string;
    fee?: string;
    fee_currency?: string;
    fee_btc?: string;
    asset?: string;
    status?: string;
    row_id?: string;
  }

  interface OwnMapping {
    name: string;
    columns: OwnColumns;
    kinds: Record<string, MappingKind>;
    zone: string;
    dollars_after_fee: ("buy" | "sell")[];
    send_fee_included: boolean;
    decimal_comma: boolean;
    day_first: boolean;
    btc_assets: string[];
    done: string[];
  }

  interface ExchangeMapping {
    id: string;
    name: string;
    ready_made: boolean;
    help: string;
    // False for a mapping built from its exchange's published format that
    // no real export has been checked against yet
    checked: boolean;
    mapping?: OwnMapping | null;
  }

  interface MappingsResponse {
    mappings: ExchangeMapping[];
  }

  interface FileColumnsResponse {
    header_row: number;
    columns: string[];
    samples: string[][];
    values: Record<string, string[]>;
    looks_like?: string | null;
  }
}

export {};
