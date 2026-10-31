import React from "react";
import { prereleaseBanner } from "../utils/prereleaseVersion";

interface PrereleaseNoticeProps {
  version: string;
  /** The Mac app (its window, or its address in a browser); unknown until the server answers. */
  desktop?: boolean;
}

/** A pre-release's banner for a version and an install (#670), or nothing for a release. */
const PrereleaseNotice: React.FC<PrereleaseNoticeProps> = ({ version, desktop }) => {
  const banner = prereleaseBanner(version, desktop);
  if (!banner) return null;
  return (
    <p className="prerelease-banner" role="note">
      <strong>{banner.title}</strong>: {banner.note}
    </p>
  );
};

export default PrereleaseNotice;
