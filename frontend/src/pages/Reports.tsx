import React, { useEffect, useState } from "react";
import api, { downloadPdfWithAxios } from "../api";
import { useToast } from "../contexts/useToast";
import { downloadFile, isDesktopApp } from "../utils/desktopDownload";
import "../styles/reports.css";

// Hardcoded base URL for your FastAPI server:
const API_BASE = "/api";

// Example list of possible reports
const REPORTS = [
  {
    key: "completeTax",
    label: "Complete Tax Report",
    description: "Gains, income, fees and year-end balances in one PDF.",
    endpoint: "/reports/complete_tax_report",
    pdfOnly: true,
    needsForms: false,
  },
  {
    key: "irsReports",
    label: "IRS Reports (Form 8949, Schedule D, etc.)",
    description: "The filled IRS forms, ready to file or hand to your preparer.",
    endpoint: "/reports/irs_reports",
    pdfOnly: true,
    needsForms: true,
  },
  {
    key: "transactionHistory",
    label: "Transaction History",
    description: "Every transaction in the year as a CSV spreadsheet.",
    endpoint: "/reports/simple_transaction_history",
    pdfOnly: false,
    needsForms: false,
  },
];

interface ReportYears {
  ledger_years: number[];
  form_years: number[] | null; // null: unknown, nothing is disabled
}

// If the year list can't be loaded, offer every year back to 2010.
function fallbackYears(): ReportYears {
  const years: number[] = [];
  for (let y = new Date().getFullYear(); y >= 2010; y--) years.push(y);
  return { ledger_years: years, form_years: null };
}

const Reports: React.FC = () => {
  // Default to Complete Tax (PDF)
  const [selectedReport, setSelectedReport] = useState<string>("completeTax");
  const [taxYear, setTaxYear] = useState<string>("");
  const [format, setFormat] = useState<string>("pdf");

  // Loading states for the spinner & progress
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [progress, setProgress] = useState<number>(0);

  const [years, setYears] = useState<ReportYears | null>(null);

  const toast = useToast();

  useEffect(() => {
    api
      .get<ReportYears>("/reports/years")
      .then((r) => setYears(r.data))
      .catch(() => setYears(fallbackYears()));
  }, []);

  const reportDef = REPORTS.find((r) => r.key === selectedReport);
  const hasForms = (year: number) =>
    !reportDef?.needsForms || years?.form_years == null || years.form_years.includes(year);
  const missingForms = taxYear !== "" && !hasForms(Number(taxYear));

  const handleExport = async () => {
    // Basic validation
    if (!taxYear) {
      toast.warning("Please enter a valid year (e.g. 2024).");
      return;
    }
    if (!reportDef) {
      toast.error("Invalid report selection.");
      return;
    }

    // If it's PDF-only but user selected CSV, override
    let finalFormat = format;
    if (reportDef.pdfOnly && format === "csv") {
      finalFormat = "pdf";
    }

    // Build final URL
    const url = `${API_BASE}${reportDef.endpoint}?year=${taxYear}&format=${finalFormat}`;

    setIsLoading(true);
    setProgress(0);

    try {
      // 1) Download as Blob with onProgress
      const blob = await downloadPdfWithAxios(url, (percent) => {
        setProgress(percent);
      });

      // 2) Build a filename
      const safeLabel = reportDef.label.replace(/\s+/g, "");
      const fileExt = finalFormat.toLowerCase() as "pdf" | "csv";
      const fileName = `${safeLabel}_${taxYear}.${fileExt}`;

      // 3) Download using desktop-aware utility
      const result = await downloadFile(blob, fileName, fileExt);

      if (result.success) {
        // Show success message with path in desktop mode
        if (isDesktopApp() && result.path) {
          toast.success(`Saved to: ${result.path}`);
        }
      } else if (result.error && result.error !== "Save cancelled") {
        // Only show error if not a user cancellation
        toast.error(`Save failed: ${result.error}`);
      }

    } catch {
      toast.error("Failed to generate the report. Please try again.");
    } finally {
      setIsLoading(false);
    }
  };

  // ------------------------------------------------------------
  // We removed the user-selectable dropdown for format.
  // Instead, we auto-set "csv" if Transaction History is chosen,
  // otherwise "pdf".
  // ------------------------------------------------------------

  return (
    <div className="reports-page">
      <h2 className="page-title">Reports</h2>

      <div className="card reports-card">
        <div className="reports-fields">
          <div className="field">
            <label htmlFor="report-tax-year">Tax year</label>
            <select
              id="report-tax-year"
              className="input"
              value={taxYear}
              onChange={(e) => setTaxYear(e.target.value)}
              disabled={years === null}
            >
              <option value="">{years === null ? "Loading…" : "Choose a year"}</option>
              {years?.ledger_years.map((y) => (
                <option key={y} value={String(y)} disabled={!hasForms(y)}>
                  {y}
                  {hasForms(y) ? "" : " (no IRS forms yet)"}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="report-format">Format</label>
            <input id="report-format" type="text" className="input report-format" readOnly value={format} />
          </div>
        </div>
        {missingForms && (
          <p className="note note-warning" role="status">
            IRS forms for {taxYear} aren't in this version of BitcoinTX yet. The Complete Tax Report
            and Transaction History work for any year.
          </p>
        )}

        <fieldset className="report-choices">
          <legend className="field-label">Report</legend>
          {REPORTS.map((r) => (
            <label key={r.key} htmlFor={r.key} className={`report-choice${selectedReport === r.key ? " selected" : ""}`}>
              <input
                type="radio"
                id={r.key}
                name="report"
                value={r.key}
                checked={selectedReport === r.key}
                onChange={() => {
                  setSelectedReport(r.key);
                  // Transaction History is a CSV; the others are PDFs
                  setFormat(r.key === "transactionHistory" ? "csv" : "pdf");
                }}
              />
              <span className="report-choice-text">
                <span className="report-choice-title">{r.label}</span>
                <span className="report-choice-description">{r.description}</span>
              </span>
            </label>
          ))}
        </fieldset>

        <div className="report-actions">
          {isLoading && (
            <div className="loading-row" role="status">
              <div className="spinner" />
              {progress > 0 ? `Downloading… ${progress}%` : "Downloading…"}
            </div>
          )}
          <button type="button" className="btn btn-primary" onClick={handleExport} disabled={isLoading || missingForms}>
            Export
          </button>
        </div>
      </div>
    </div>
  );
};

export default Reports;
