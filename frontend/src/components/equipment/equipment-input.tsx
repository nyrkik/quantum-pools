"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { api } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Loader2 } from "lucide-react";

interface EquipmentModel {
  normalized_name: string;
  brand: string | null;
  model: string | null;
  part_number: string | null;
  count: number;
}

interface EquipmentInputProps {
  value: string;
  onChange: (value: string) => void;
  equipmentType: "pump" | "filter" | "heater" | "chlorinator" | "automation";
  className?: string;
  placeholder?: string;
}

export function EquipmentInput({
  value,
  onChange,
  equipmentType,
  className = "",
  placeholder,
}: EquipmentInputProps) {
  const [query, setQuery] = useState(value ?? "");
  const [suggestions, setSuggestions] = useState<EquipmentModel[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(-1);
  const containerRef = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  // Sync external value changes
  useEffect(() => {
    setQuery(value ?? "");
  }, [value]);

  const fetchSuggestions = useCallback(
    async (q: string) => {
      if (q.length < 3) {
        setSuggestions([]);
        return;
      }
      setLoading(true);
      try {
        const data = await api.get<EquipmentModel[]>(
          `/v1/equipment/models?type=${encodeURIComponent(equipmentType)}&q=${encodeURIComponent(q)}`
        );
        setSuggestions(data);
        setOpen(data.length > 0);
        setSelectedIndex(-1);
      } catch {
        setSuggestions([]);
      } finally {
        setLoading(false);
      }
    },
    [equipmentType]
  );

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    setQuery(val);
    onChange(val);

    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => fetchSuggestions(val), 250);
  };

  const handleSelect = (model: EquipmentModel) => {
    const val = model.normalized_name;
    setQuery(val);
    onChange(val);
    setOpen(false);
    setSuggestions([]);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!open || suggestions.length === 0) return;

    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIndex((prev) => Math.min(prev + 1, suggestions.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIndex((prev) => Math.max(prev - 1, 0));
    } else if (e.key === "Enter" && selectedIndex >= 0) {
      e.preventDefault();
      handleSelect(suggestions[selectedIndex]);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  };

  // Close on outside click
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  return (
    <div ref={containerRef} className="relative">
      <div className="relative">
        <Input
          value={query}
          onChange={handleInputChange}
          onKeyDown={handleKeyDown}
          onFocus={() => {
            if (suggestions.length > 0) setOpen(true);
          }}
          className={className}
          placeholder={placeholder}
          autoComplete="off"
        />
        {loading && (
          <Loader2 className="absolute right-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 animate-spin text-muted-foreground" />
        )}
      </div>
      {open && suggestions.length > 0 && (
        <div className="absolute z-50 left-0 right-0 sm:right-auto sm:min-w-[320px] mt-1 bg-popover border border-border rounded-md shadow-lg max-h-64 overflow-y-auto">
          {suggestions.map((model, i) => (
            <button
              key={`${model.normalized_name}-${i}`}
              type="button"
              className={`w-full text-left px-3 py-3 hover:bg-accent hover:text-accent-foreground cursor-pointer border-b last:border-0 ${
                i === selectedIndex ? "bg-accent text-accent-foreground" : ""
              }`}
              onMouseDown={(e) => {
                e.preventDefault();
                handleSelect(model);
              }}
            >
              <p className="text-sm font-medium leading-tight">
                {model.normalized_name}
              </p>
              <div className="flex items-center gap-2 mt-0.5">
                {model.brand && (
                  <span className="text-xs text-muted-foreground">{model.brand}</span>
                )}
                {model.part_number && (
                  <span className="text-xs text-muted-foreground font-mono">#{model.part_number}</span>
                )}
                <span className="text-[10px] text-muted-foreground ml-auto">{model.count} in system</span>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
