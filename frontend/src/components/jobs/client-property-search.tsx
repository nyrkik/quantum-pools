"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { X } from "lucide-react";

interface ClientPropertySearchProps {
  customerName: string;
  propertyAddress: string;
  onChange: (name: string, address: string, customerId?: string) => void;
}

export function ClientPropertySearch({
  customerName,
  propertyAddress,
  onChange,
}: ClientPropertySearchProps) {
  const [query, setQuery] = useState(customerName);
  const [results, setResults] = useState<
    {
      customer_id: string;
      customer_name: string;
      property_address: string;
      property_name: string | null;
    }[]
  >([]);
  const [showResults, setShowResults] = useState(false);

  useEffect(() => {
    if (query.length < 2) {
      setResults([]);
      return;
    }
    const timer = setTimeout(async () => {
      try {
        const data = await api.get<
          {
            customer_id: string;
            customer_name: string;
            property_address: string;
            property_name: string | null;
          }[]
        >(`/v1/admin/client-search?q=${encodeURIComponent(query)}`);
        setResults(data);
        setShowResults(true);
      } catch {
        setResults([]);
      }
    }, 250);
    return () => clearTimeout(timer);
  }, [query]);

  const [manualAddress, setManualAddress] = useState(false);

  return (
    <div className="space-y-2">
      <div className="relative">
        <div className="relative">
          <Input
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              onChange(e.target.value, propertyAddress);
            }}
            placeholder="Client name (search or type)"
            className="text-sm h-8 pr-7"
            onFocus={() => results.length > 0 && setShowResults(true)}
          />
          {(query || propertyAddress) && (
            <button
              type="button"
              className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              onClick={() => { setQuery(""); onChange("", ""); setManualAddress(false); setResults([]); }}
            >
              <X className="h-3 w-3" />
            </button>
          )}
        </div>
        {showResults && results.length > 0 && (
          <>
            <div
              className="fixed inset-0 z-40"
              onClick={() => setShowResults(false)}
            />
            <div className="absolute top-full left-0 right-0 z-50 mt-1 max-h-48 overflow-y-auto rounded-md border bg-background shadow-lg">
              {results.map((r, i) => (
                <button
                  key={i}
                  type="button"
                  className="w-full px-3 py-2 text-left hover:bg-muted/50 text-sm"
                  onClick={() => {
                    setQuery(r.customer_name);
                    onChange(r.customer_name, r.property_address, r.customer_id);
                    setShowResults(false);
                    setManualAddress(false);
                  }}
                >
                  <span className="font-medium">{r.customer_name}</span>
                  {r.property_name && (
                    <span className="text-muted-foreground ml-1">
                      ({r.property_name})
                    </span>
                  )}
                  <span className="text-xs text-muted-foreground block">
                    {r.property_address}
                  </span>
                </button>
              ))}
            </div>
          </>
        )}
      </div>
      {propertyAddress && !manualAddress ? (
        <p className="text-xs text-muted-foreground px-1 cursor-pointer hover:text-foreground" onClick={() => setManualAddress(true)}>
          {propertyAddress}
        </p>
      ) : (
        <Input
          value={propertyAddress}
          onChange={(e) => onChange(query, e.target.value)}
          placeholder="Address"
          className="text-sm h-8"
        />
      )}
    </div>
  );
}
