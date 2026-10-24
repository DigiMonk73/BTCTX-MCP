import React from "react";
import type { SettingsSectionId } from "../utils/settingsSections";
import Chevron from "./Chevron";

interface SettingsSectionProps {
  id: SettingsSectionId;
  title: string;
  /** The region's name, where tests and docs know it otherwise ("Ledger review"); else the title. */
  region?: string;
  /** One line under the title: what's inside, or how it stands. */
  summary: string;
  open: boolean;
  onToggle: (id: SettingsSectionId) => void;
  className?: string;
  children: React.ReactNode;
}

/**
 * One of Settings' sections (#355, P7's mockups): a button with the title
 * and its summary, which opens and closes the section. A closed section
 * stays mounted, hidden: what it loads, and a form or preview left half
 * done, are as they were when it opens again.
 */
const SettingsSection: React.FC<SettingsSectionProps> = ({
  id, title, region, summary, open, onToggle, className, children,
}) => {
  const body = `settings-${id}`;
  return (
    <section className="settings-section" id={`${body}-section`}>
      <h3 className="settings-section-heading">
        <button
          type="button"
          className="settings-section-toggle chevron-toggle"
          aria-expanded={open}
          aria-controls={body}
          aria-labelledby={`${body}-title`}
          aria-describedby={`${body}-summary`}
          onClick={() => onToggle(id)}
        >
          <span className="settings-section-text">
            <span id={`${body}-title`} className="settings-section-title">{title}</span>
            <span id={`${body}-summary`} className="settings-section-summary">{summary}</span>
          </span>
          <Chevron />
        </button>
      </h3>
      <div
        id={body}
        role="region"
        aria-label={region ?? title}
        className={className ? `settings-section-body ${className}` : "settings-section-body"}
        hidden={!open}
      >
        {children}
      </div>
    </section>
  );
};

export default SettingsSection;
