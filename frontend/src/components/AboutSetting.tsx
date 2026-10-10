import React, { useEffect, useState } from "react";
import api from "../api";

const REPO = "https://github.com/DigiMonk73/BTCTX-MCP";

/** The project's pages this section links to (SECURITY.md, README "Reporting problems"). */
const ABOUT_LINKS = {
  report: `${REPO}/issues/new/choose`,
  knownIssues: `${REPO}/issues?q=is%3Aissue+is%3Aopen+label%3Abug`,
  security: `${REPO}/security/advisories/new`,
  releases: `${REPO}/releases`,
};

const Outside: React.FC<{ href: string; children: React.ReactNode }> = ({ href, children }) => (
  <a className="link" href={href} target="_blank" rel="noreferrer">
    {children}
  </a>
);

/**
 * About BitcoinTX: the version a bug report asks for, and where to report a
 * problem. Links only: nothing is sent anywhere until the owner clicks one.
 */
const AboutSetting: React.FC = () => {
  const [version, setVersion] = useState<string | undefined>();

  useEffect(() => {
    api
      .get<{ version?: string }>("/health")
      .then((res) => setVersion(res.data.version))
      .catch(() => undefined);
  }, []);

  return (
    <div className="settings-section" role="region" aria-label="About BitcoinTX">
      <h3 className="section-title">About BitcoinTX</h3>
      <p className="settings-option-subtitle">Version {version ?? "unknown"}</p>
      <p className="settings-option-subtitle">
        <Outside href={ABOUT_LINKS.report}>Report a problem</Outside>: a bug, or a figure that looks
        wrong. Reports are public, so never include your own figures or addresses. Already known:{" "}
        <Outside href={ABOUT_LINKS.knownIssues}>open issues</Outside>.
      </p>
      <p className="settings-option-subtitle">
        A security problem? <Outside href={ABOUT_LINKS.security}>Report it privately</Outside>, never
        in a public report. What changed in each version:{" "}
        <Outside href={ABOUT_LINKS.releases}>release notes</Outside>.
      </p>
    </div>
  );
};

export default AboutSetting;
