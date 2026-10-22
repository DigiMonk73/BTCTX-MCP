import React from "react";
import { priceMomentLine } from "../../utils/converter";

/** Date mode's line under the date and hour (#555): which price shows, the reason
 * too for a screen reader, which is told as it changes. Empty while the hour's
 * answer comes, so the calculator below doesn't move. */
const PriceMomentLine: React.FC<{ answer: { moment?: string; at?: string } | null }> = ({ answer }) => {
  const line = answer && priceMomentLine(answer.moment, answer.at);
  return (
    <p className="converter-note price-moment-line" aria-live="polite" title={line?.why ?? undefined}>
      {line && <span>{line.text}</span>}
      {line?.why && <span className="sr-only"> {line.why}</span>}
    </p>
  );
};

export default PriceMomentLine;
