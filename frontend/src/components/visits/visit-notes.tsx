"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import { Textarea } from "@/components/ui/textarea";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { ChevronDown, ChevronUp } from "lucide-react";

interface VisitNotesProps {
  notes: string;
  onChange: (notes: string) => void;
}

export function VisitNotes({ notes, onChange }: VisitNotesProps) {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState(notes);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  useEffect(() => {
    setValue(notes);
  }, [notes]);

  const handleChange = useCallback(
    (text: string) => {
      setValue(text);
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => onChange(text), 1000);
    },
    [onChange]
  );

  const handleBlur = useCallback(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    onChange(value);
  }, [value, onChange]);

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger asChild>
        <button className="flex w-full items-center justify-between rounded-lg bg-muted/60 px-4 py-3 text-left">
          <div className="flex items-center gap-3">
            <span className="text-sm font-semibold">Notes</span>
            {value && <span className="text-xs text-muted-foreground">has notes</span>}
          </div>
          {open ? <ChevronUp className="h-4 w-4 text-muted-foreground" /> : <ChevronDown className="h-4 w-4 text-muted-foreground" />}
        </button>
      </CollapsibleTrigger>

      <CollapsibleContent>
        <div className="pt-2">
          <Textarea
            value={value}
            onChange={(e) => handleChange(e.target.value)}
            onBlur={handleBlur}
            placeholder="Visit notes..."
            rows={3}
            className="text-sm"
          />
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}
