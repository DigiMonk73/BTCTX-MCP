import React from "react";

/** A card while its figures load: its title and a spinner, at its size, so nothing jumps. */
const LoadingCard: React.FC<{ title: string; className?: string }> = ({ title, className = "" }) => (
  <div className={`card ${className}`}>
    <h3 className="card-title">{title}</h3>
    <div className="loading-row">
      <div className="spinner" /> Loading…
    </div>
  </div>
);

export default LoadingCard;
