// The CSV and River imports' previews and results, as the server sends them.

declare global {
  // The CSV import's preview (POST /api/import/preview) and status.
  interface CSVRowPreview {
    row_number: number;
    date: string;
    type: string;
    amount: string;
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
    status: "new" | "matched" | "discrepancy";
    matched_tx_id?: number;
    discrepancy?: string;
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
  }

  interface RiverImportResponse {
    success: boolean;
    imported_count: number;
    skipped_existing: number;
    message: string;
  }
}

export {};
