"use client";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Search, Building2, Home } from "lucide-react";

interface CustomerFilterBarProps {
  search: string;
  onSearchChange: (value: string) => void;
  typeFilter: string | null;
  onTypeFilterChange: (value: string | null) => void;
  statusFilter: Set<string>;
  onStatusFilterChange: (value: Set<string>) => void;
}

const TYPE_OPTIONS = [
  { value: "commercial", label: "Commercial", icon: Building2 },
  { value: "residential", label: "Residential", icon: Home },
] as const;

const STATUS_OPTIONS = [
  { value: "active", label: "Active" },
  { value: "service_call", label: "Service Call" },
  { value: "lead", label: "Lead" },
  { value: "inactive", label: "Inactive" },
] as const;

export function CustomerFilterBar({
  search,
  onSearchChange,
  typeFilter,
  onTypeFilterChange,
  statusFilter,
  onStatusFilterChange,
}: CustomerFilterBarProps) {
  return (
    <>
      <div className="flex items-center gap-2">
        <Search className="h-4 w-4 text-muted-foreground" />
        <Input
          placeholder="Search clients..."
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          className="max-w-sm"
        />
      </div>

      <div className="flex items-center gap-2">
        <div className="flex items-center gap-1.5">
          {TYPE_OPTIONS.map((t) => (
            <Button
              key={t.value}
              variant={typeFilter === t.value ? "default" : "outline"}
              size="sm"
              className="h-7 px-2.5 text-xs"
              onClick={() => onTypeFilterChange(typeFilter === t.value ? null : t.value)}
            >
              <t.icon className="h-3.5 w-3.5 mr-1" />{t.label}
            </Button>
          ))}
        </div>
        <div className="flex-1" />
        <div className="flex items-center gap-1.5">
          {STATUS_OPTIONS.map((s) => (
            <Button
              key={s.value}
              variant={statusFilter.has(s.value) ? "default" : "outline"}
              size="sm"
              className="h-7 px-2.5 text-xs"
              onClick={() => {
                const next = new Set(statusFilter);
                if (next.has(s.value)) next.delete(s.value);
                else next.add(s.value);
                onStatusFilterChange(next);
              }}
            >
              {s.label}
            </Button>
          ))}
        </div>
      </div>
    </>
  );
}
