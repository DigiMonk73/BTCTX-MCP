import React from "react";

interface FigureRowProps {
  label: string;
  className?: string;
  children: React.ReactNode;
}

/** A dashboard figure: its label on the left, the value on the right. */
const FigureRow: React.FC<FigureRowProps> = ({ label, className, children }) => (
  <p>
    <strong>{label}</strong>
    <span className={className}>{children}</span>
  </p>
);

export default FigureRow;
