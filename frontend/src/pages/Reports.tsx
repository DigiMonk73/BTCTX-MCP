import React, { useEffect, useState } from "react";
import api, { downloadPdfWithAxios } from "../api";
import { useToast } from "../contexts/useToast";
import { downloadFile, isDesktopApp } from "../utils/desktopDownload";
import { reportErrorMessage } from "../utils/reportError";
import "../styles/reports.css";

const API_BASE = "/api";

const REPORTS = [
  {
    key: "completeTax",
    label: "Complete Tax Report",
    description: "Gains, income, gifts and holdings, with a one-page summary. PDF.",
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
    description: "Every transaction in the year, as a CSV spreadsheet or a PDF.",
    endpoint: "/reports/simple_transaction_history",
    pdfOnly: false,
    needsForms: false,
  },
];

type ReportFormat = "pdf" | "csv";

interface ReportYears {
  ledger_years: number[];
  form_years: number[] | null; // null: unknown, nothing is disabled
  draft_years?: number[]; // the IRS's draft forms: a preview, not for filing
}

// If the year list can't be loaded, offer every year back to 2010.
function fallbackYears(): ReportYears {
  const years: number[] = [];
  for (let y = new Date().getFullYear(); y >= 2010; y--) years.push(y);
  return { ledger_years: years, form_years: null };
}

const Reports: React.FC = () => {
  const [selectedReport, setSelectedReport] = useState<string>("completeTax");
  const [taxYear, setTaxYear] = useState<string>("");
  const [format, setFormat] = useState<ReportFormat>("pdf");

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
  const isDraft = (year: number) => !!reportDef?.needsForms && !!years?.draft_years?.includes(year);
  // A year after every year with forms: its final forms come in an update
  const formsToCome = (year: number) => year > Math.max(0, ...(years?.form_years ?? []));

  const handleExport = async () => {
    if (!taxYear) {
      toast.warning("Please enter a valid year (e.g. 2024).");
      return;
    }
    if (!reportDef) {
      toast.error("Invalid report selection.");
      return;
    }

    let finalFormat: ReportFormat = format;
    if (reportDef.pdfOnly && format === "csv") {
      finalFormat = "pdf";
    }

    const url = `${API_BASE}${reportDef.endpoint}?year=${taxYear}&format=${finalFormat}`;

    setIsLoading(true);
    setProgress(0);

    try {
      const blob = await downloadPdfWithAxios(url, (percent) => {
        setProgress(percent);
      });

      const safeLabel = reportDef.label.replace(/\s+/g, "");
      const fileExt = finalFormat;
      const fileName = `${safeLabel}_${taxYear}.${fileExt}`;

      const result = await downloadFile(blob, fileName, fileExt);

      if (result.success) {
        // A browser shows its own download; the Mac app says where it saved
        if (isDesktopApp() && result.path) {
          toast.success(`Saved to: ${result.path}`);
        }
      } else if (result.error && result.error !== "Save cancelled") {
        toast.error(`Save failed: ${result.error}`);
      }

    } catch (error) {
      toast.error(await reportErrorMessage(error));
    } finally {
      setIsLoading(false);
    }
  };

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
                  {hasForms(y) ? (isDraft(y) ? " – IRS draft (preview, not for filing)" : "") : " (no IRS forms yet)"}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="report-format">Format</label>
            {reportDef?.pdfOnly ? (
              <input id="report-format" type="text" className="input report-format" readOnly value={format} />
            ) : (
              <select
                id="report-format"
                className="input"
                value={format}
                onChange={(e) => setFormat(e.target.value === "pdf" ? "pdf" : "csv")}
              >
                <option value="csv">CSV spreadsheet</option>
                <option value="pdf">PDF</option>
              </select>
            )}
          </div>
        </div>
        {missingForms && (
          <p className="note note-warning" role="status">
            {formsToCome(Number(taxYear))
              ? `Update BitcoinTX to get the final IRS forms for ${taxYear} (the IRS usually publishes them in December or January).`
              : `IRS forms for ${taxYear} aren't in this version of BitcoinTX yet.`}{" "}
            The Complete Tax Report and Transaction History work for any year.
          </p>
        )}
        {taxYear !== "" && isDraft(Number(taxYear)) && (
          <p className="note note-warning" role="status">
            Preview: these are the IRS's draft {taxYear} forms, marked DRAFT — DO NOT FILE on every
            page. Don't file them: update BitcoinTX for the final forms once the IRS publishes them. The
            preview ends on January 1, {Number(taxYear) + 1}.
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
                  // Transaction History starts as a CSV (it can be a PDF); the others are PDFs
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
