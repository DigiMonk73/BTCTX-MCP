// Every page of a 2.0 pre-release, an alpha or a beta, the login page
// included: which test version this is, so it can't be taken for BitcoinTX
// itself (#670). Whether it is the Mac app, BitcoinTX Preview, comes from the
// server (setup-status, asked before anyone logs in).
import React, { useEffect, useState } from "react";
import api from "../api";
import type { SetupStatus } from "../utils/credentials";
import { prereleaseBanner } from "../utils/prereleaseVersion";

interface NoticeProps {
  version: string;
  /** The Mac app (its window, or its address in a browser); unknown until the server answers. */
  desktop?: boolean;
}

/** The banner for a version and an install, or nothing for a release. */
export const PrereleaseNotice: React.FC<NoticeProps> = ({ version, desktop }) => {
  const banner = prereleaseBanner(version, desktop);
  if (!banner) return null;
  return (
    <p className="prerelease-banner" role="note">
      <strong>{banner.title}</strong>: {banner.note}
    </p>
  );
};

const PrereleaseBanner: React.FC = () => {
  const prerelease = prereleaseBanner(__BTCTX_VERSION__) !== null;
  // Shown once the server has said which install this is, so the Mac's
  // name never replaces a server's on screen; unanswered, it claims neither
  const [answered, setAnswered] = useState<{ desktop?: boolean } | null>(null);

  useEffect(() => {
    if (!prerelease) return;
    api
      .get<SetupStatus>("/users/setup-status")
      .then((res) => setAnswered({ desktop: Boolean(res.data.desktop) }))
      .catch(() => setAnswered({}));
  }, [prerelease]);

  if (!answered) return null;
  return <PrereleaseNotice version={__BTCTX_VERSION__} desktop={answered.desktop} />;
};

export default PrereleaseBanner;
