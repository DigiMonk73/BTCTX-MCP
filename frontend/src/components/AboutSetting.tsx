import React, { useEffect, useState } from "react";
import axios from "axios";
import api from "../api";
import { REPO_URL } from "../utils/aiSetup";

/** The project's pages this section links to (SECURITY.md, README "Reporting problems"). */
const ABOUT_LINKS = {
  releases: `${REPO_URL}/releases`,
  report: `${REPO_URL}/issues/new/choose`,
  knownBugs: `${REPO_URL}/issues?q=is%3Aissue+is%3Aopen+label%3Abug`,
  security: `${REPO_URL}/security/advisories/new`,
};

const Outside: React.FC<{ href: string; children: React.ReactNode }> = ({ href, children }) => (
  <a className="link" href={href} target="_blank" rel="noreferrer">
    {children}
  </a>
);

/** The version from /api/health: undefined while it loads, null when unknown. */
function useAppVersion(): string | null | undefined {
  const [version, setVersion] = useState<string | null | undefined>();
  useEffect(() => {
    api
      .get<{ version?: string }>("/health")
      .then((res) => setVersion(res.data.version ?? null))
      // a 503 (database down) still names the version
      .catch((err) => setVersion((axios.isAxiosError(err) && err.response?.data?.version) || null));
  }, []);
  return version;
}

/**
 * About BitcoinTX: the version a bug report asks for, and where to report a
 * problem. Links only: nothing is sent anywhere until the owner clicks one.
 */
const AboutSetting: React.FC = () => {
  const version = useAppVersion();

  return (
    <div className="settings-section about-section" role="region" aria-label="About BitcoinTX">
      <h3 className="section-title">About BitcoinTX</h3>
      <p className="settings-option-subtitle">
        Version {version === undefined ? "…" : (version ?? "unknown")} ·{" "}
        <Outside href={ABOUT_LINKS.releases}>release notes</Outside>
      </p>
      <p className="settings-option-subtitle">
        <Outside href={ABOUT_LINKS.report}>Report a problem</Outside>: a bug, or a figure that looks
        wrong. Reports are public, so never include your own figures or addresses. Already known:{" "}
        <Outside href={ABOUT_LINKS.knownBugs}>open bugs</Outside>.
      </p>
      <p className="settings-option-subtitle">
        A security problem? <Outside href={ABOUT_LINKS.security}>Report it privately</Outside>, never
        in a public report.
      </p>
    </div>
  );
};

export default AboutSetting;
