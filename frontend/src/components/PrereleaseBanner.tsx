// Every page of a 2.0 pre-release, an alpha or a beta, the login page
// included: which test version this is, so it can't be taken for BitcoinTX
// itself (#670). Whether it is the Mac app, BitcoinTX Preview, comes from the
// server (setup-status, asked before anyone logs in).
import React, { useEffect, useState } from "react";
import api from "../api";
import type { SetupStatus } from "../utils/credentials";
import { prereleaseParts } from "../utils/prereleaseVersion";
import PrereleaseNotice from "./PrereleaseNotice";

const PrereleaseBanner: React.FC = () => {
  const prerelease = prereleaseParts(__BTCTX_VERSION__) !== null;
  // Unknown until the server answers: the banner shows at once, claiming
  // neither install, so the page never moves down under the user's pointer
  // when it arrives (a server reached over Tor answers slowly)
  const [desktop, setDesktop] = useState<boolean | undefined>(undefined);

  useEffect(() => {
    if (!prerelease) return;
    api
      .get<SetupStatus>("/users/setup-status")
      .then((res) => setDesktop(Boolean(res.data.desktop)))
      .catch(() => undefined);
  }, [prerelease]);

  return <PrereleaseNotice version={__BTCTX_VERSION__} desktop={desktop} />;
};

export default PrereleaseBanner;
