import React from "react";
import { ChevronDown } from "lucide-react";

/** The chevron of a button that opens and closes what's under it, the one
 * chevron in the app (#674): Settings' sections and account rows and the
 * dashboard's lines. One icon and size, styled by components.css's
 * `.chevron` inside a `.chevron-toggle` button. */
const Chevron: React.FC = () => <ChevronDown className="chevron" size={20} aria-hidden="true" />;

export default Chevron;
