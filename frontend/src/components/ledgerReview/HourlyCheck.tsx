import React, { useState } from "react";
import type { HourlyPick, HourlyYear, ReviewCheck, ReviewItem } from "./types";

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;

/** "+$1000.10" or "−$3.00" */
function signed(value: string): string {
  return value.startsWith("-") ? `−$${value.slice(1)}` : `+$${value}`;
}

/** A year's totals that move, e.g. "income +$1000.10, fee values +$1.00" */
function yearTotals(y: HourlyYear): string {
  const parts: [string, string][] = [
    ["income", y.income], ["basis", y.basis], ["proceeds", y.proceeds], ["fee values", y.fees],
  ];
  const moved = parts.filter(([, v]) => Number(v) !== 0).map(([name, v]) => `${name} ${signed(v)}`);
  return moved.length ? moved.join(", ") : "less than a cent";
}

const ItemRow: React.FC<{ item: ReviewItem; ticked: boolean; onTick: (id: number) => void }> = (
  { item, ticked, onTick },
) => (
  <li>
    <label>
      <input type="checkbox" checked={ticked} onChange={() => onTick(item.id)} /> #{item.id} · {item.date} ·{" "}
      {item.type} ({item.type === "Deposit" ? item.source : item.purpose}) · {item.amount} BTC — {item.issue}{" "}
      {item.change}
    </label>
  </li>
);

interface YearProps {
  check: ReviewCheck;
  year: HourlyYear;
  ticked: Set<number>;
  onTick: (id: number) => void;
  busy: boolean;
  onApply: (pick: HourlyPick, question: string) => void;
}

/** One tax year: what changes, its listed items, and a button for all of it. */
const YearGroup: React.FC<YearProps> = ({ check, year, ticked, onTick, busy, onApply }) => {
  const items = check.items.filter((i) => i.year === year.year);
  const unlisted = year.count - year.listed;
  const applyYear = () =>
    onApply(
      { year: year.year },
      `Change all ${plural(year.count, "transaction")} of ${year.year} to the price of their hour (that day's ` +
        `where there's none) and recalculate the ledger?\n\nThis changes ${year.year}'s totals: ` +
        `${yearTotals(year)}. If you already filed ${year.year}, these are figures on a filed return: whether ` +
        "to amend is a question for a tax professional. A backup copy of the database is made first.",
    );
  return (
    <div role="group" aria-label={`Tax year ${year.year}`}>
      <p className="settings-option-subtitle">
        <strong>{year.year}</strong>: {plural(year.count, "transaction")}
        {unlisted > 0 && ` (${unlisted} changing by less than $1.00 each, not listed)`}. Totals: {yearTotals(year)}.
      </p>
      {items.length > 0 && (
        <ul aria-label={`${check.title}, ${year.year}`}>
          {items.map((item) => (
            <ItemRow key={item.id} item={item} ticked={ticked.has(item.id)} onTick={onTick} />
          ))}
        </ul>
      )}
      <button onClick={applyYear} disabled={busy} className="btn btn-secondary">
        Apply to all of {year.year}
      </button>
    </div>
  );
};

/**
 * Ledger Review's check of values priced at the day (#144): by tax year,
 * each listed transaction with a box to tick, and buttons to apply the
 * ticked ones or a whole year. It changes tax figures, so it asks first.
 */
const HourlyCheck: React.FC<{ check: ReviewCheck; busy: boolean; onApply: YearProps["onApply"] }> = (
  { check, busy, onApply },
) => {
  const [ticked, setTicked] = useState<Set<number>>(new Set());
  const tick = (id: number) => {
    const next = new Set(ticked);
    if (!next.delete(id)) next.add(id);
    setTicked(next);
  };
  // Only those still listed: an applied one is gone after the review reloads
  const picked = check.items.filter((i) => ticked.has(i.id)).map((i) => i.id);
  const applyTicked = () =>
    onApply(
      { ids: picked },
      `Change the ${plural(picked.length, "ticked transaction")} to the values shown and recalculate the ` +
        "ledger?\n\nThis changes their tax figures. A backup copy of the database is made first.",
    );
  return (
    <div className="ledger-review-check">
      <strong>
        {check.title}: {check.count}
      </strong>
      {check.explanation.map((paragraph) => (
        <p key={paragraph} className="settings-option-subtitle">
          {paragraph}
        </p>
      ))}
      {(check.years ?? []).map((year) => (
        <YearGroup key={year.year} {...{ check, year, ticked, onTick: tick, busy, onApply }} />
      ))}
      <p className="settings-option-subtitle">{check.action}</p>
      <button onClick={applyTicked} disabled={busy || picked.length === 0} className="btn btn-primary">
        Apply to the ticked ones
      </button>
    </div>
  );
};

export default HourlyCheck;
