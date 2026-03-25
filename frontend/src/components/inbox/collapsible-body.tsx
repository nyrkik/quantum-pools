"use client";

import { useState } from "react";
import { ChevronDown } from "lucide-react";

export function CollapsibleBody({ text }: { text: string }) {
  const [expanded, setExpanded] = useState(false);

  // Short messages (one line) don't need collapse
  if (text.length < 80 && !text.includes('\n')) {
    return <div className="whitespace-pre-wrap text-sm leading-relaxed">{text}</div>;
  }

  return (
    <div
      className="cursor-pointer"
      onClick={() => setExpanded(!expanded)}
    >
      <div className={`whitespace-pre-wrap text-sm leading-relaxed ${expanded ? "" : "max-h-[5.5rem] overflow-hidden"}`}>
        {text}
      </div>
      <ChevronDown className={`h-3 w-3 text-muted-foreground mx-auto mt-0.5 transition-transform ${expanded ? "rotate-180" : ""}`} />
    </div>
  );
}
