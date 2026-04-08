"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Search, X, UserPlus } from "lucide-react";
import { api } from "@/lib/api";

interface CustomerOption {
  id: string;
  name: string;
}

interface CustomerPickerProps {
  /** Pre-filled customer from AI or context */
  initialCustomerId?: string | null;
  initialCustomerName?: string | null;
  /** Callback when selection changes */
  onChange: (customerId: string | null, billingName: string | null) => void;
  /** Compact mode for inline use */
  compact?: boolean;
}

export function CustomerPicker({
  initialCustomerId,
  initialCustomerName,
  onChange,
  compact = false,
}: CustomerPickerProps) {
  const [mode, setMode] = useState<"selected" | "search" | "custom">(
    initialCustomerId ? "selected" : "search"
  );
  const [selectedId, setSelectedId] = useState<string | null>(initialCustomerId || null);
  const [selectedName, setSelectedName] = useState<string | null>(initialCustomerName || null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<CustomerOption[]>([]);
  const [searching, setSearching] = useState(false);
  const [customName, setCustomName] = useState("");
  const [showDropdown, setShowDropdown] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Sync initial values when they change (e.g. AI resolves customer)
  useEffect(() => {
    if (initialCustomerId && initialCustomerId !== selectedId) {
      setSelectedId(initialCustomerId);
      setSelectedName(initialCustomerName || null);
      setMode("selected");
    }
  }, [initialCustomerId, initialCustomerName]);

  const doSearch = useCallback(async (q: string) => {
    if (q.length < 2) { setResults([]); return; }
    setSearching(true);
    try {
      const data = await api.get<{ customer_id: string; customer_name: string; property_address?: string }[]>(
        `/v1/admin/agent-threads/client-search?q=${encodeURIComponent(q)}`
      );
      // Dedupe by customer_id (endpoint returns per-property rows)
      const seen = new Set<string>();
      const deduped: CustomerOption[] = [];
      for (const c of data) {
        if (!seen.has(c.customer_id)) {
          seen.add(c.customer_id);
          deduped.push({ id: c.customer_id, name: c.customer_name });
        }
      }
      setResults(deduped);
      setShowDropdown(true);
    } catch {
      setResults([]);
    } finally {
      setSearching(false);
    }
  }, []);

  const handleQueryChange = (value: string) => {
    setQuery(value);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => doSearch(value), 300);
  };

  const selectCustomer = (c: CustomerOption) => {
    setSelectedId(c.id);
    setSelectedName(c.name);
    setMode("selected");
    setShowDropdown(false);
    setQuery("");
    onChange(c.id, null);
  };

  const clearSelection = () => {
    setSelectedId(null);
    setSelectedName(null);
    setMode("search");
    setQuery("");
    onChange(null, null);
  };

  const enterCustomMode = () => {
    setMode("custom");
    setShowDropdown(false);
    setQuery("");
    onChange(null, customName || null);
  };

  const handleCustomNameChange = (value: string) => {
    setCustomName(value);
    onChange(null, value || null);
  };

  // Close dropdown on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setShowDropdown(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const textSize = compact ? "text-xs" : "text-sm";

  if (mode === "selected" && selectedName) {
    return (
      <div className={`flex items-center gap-2 ${textSize}`}>
        <span className="font-medium truncate">{selectedName}</span>
        <Button variant="ghost" size="icon" className="h-5 w-5 shrink-0" onClick={clearSelection}>
          <X className="h-3 w-3" />
        </Button>
      </div>
    );
  }

  if (mode === "custom") {
    return (
      <div className="space-y-1.5">
        <Input
          value={customName}
          onChange={(e) => handleCustomNameChange(e.target.value)}
          placeholder="Customer name (not in system)"
          className={`h-8 ${textSize}`}
          autoFocus
        />
        <button
          type="button"
          className={`${textSize} text-muted-foreground hover:text-foreground underline`}
          onClick={() => { setMode("search"); onChange(null, null); }}
        >
          Search existing customers instead
        </button>
      </div>
    );
  }

  // Search mode
  return (
    <div ref={containerRef} className="relative space-y-1.5">
      <div className="relative">
        <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
        <Input
          value={query}
          onChange={(e) => handleQueryChange(e.target.value)}
          placeholder="Search customers..."
          className={`h-8 pl-7 pr-2 ${textSize}`}
          autoFocus
          onFocus={() => { if (results.length > 0) setShowDropdown(true); }}
        />
      </div>
      {showDropdown && (results.length > 0 || query.length >= 2) && (
        <div className="absolute z-50 w-full bg-background border rounded-md shadow-md max-h-48 overflow-y-auto mt-0.5">
          {results.map((c) => (
            <button
              key={c.id}
              type="button"
              className={`w-full text-left px-3 py-2 hover:bg-muted/50 ${textSize} truncate`}
              onClick={() => selectCustomer(c)}
            >
              {c.name}
            </button>
          ))}
          {query.length >= 2 && results.length === 0 && !searching && (
            <div className={`px-3 py-2 ${textSize} text-muted-foreground`}>No matches</div>
          )}
          <button
            type="button"
            className={`w-full text-left px-3 py-2 hover:bg-muted/50 ${textSize} text-muted-foreground flex items-center gap-1.5 border-t`}
            onClick={enterCustomMode}
          >
            <UserPlus className="h-3 w-3" />
            Not in system — enter name
          </button>
        </div>
      )}
      {!showDropdown && (
        <button
          type="button"
          className={`${textSize} text-muted-foreground hover:text-foreground underline`}
          onClick={enterCustomMode}
        >
          Customer not in system?
        </button>
      )}
    </div>
  );
}
