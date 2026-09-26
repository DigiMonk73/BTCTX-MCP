// src/components/PortBanner.tsx
// Mac app only: a persistent notice when this session runs on another port
// than the usual one (the user chose it because the port was taken), since
// AI assistants look for BitcoinTX on the usual port.
import React, { useEffect, useState } from "react";
import api from "../api";

interface DesktopInfo {
  desktop: boolean;
  port: number | null;
  preferred_port: number | null;
  port_fallback: boolean;
}

const PortBanner: React.FC = () => {
  const [info, setInfo] = useState<DesktopInfo | null>(null);

  useEffect(() => {
    api
      .get<DesktopInfo>("/settings/desktop")
      .then((res) => setInfo(res.data))
      .catch(() => undefined);
  }, []);

  if (!info?.port_fallback) return null;
  return (
    <div className="port-banner" role="alert">
      BitcoinTX is running on port {info.port} this session because port{" "}
      {info.preferred_port} was taken. AI assistants can't connect until you quit
      BitcoinTX and open it again.
    </div>
  );
};

export default PortBanner;
