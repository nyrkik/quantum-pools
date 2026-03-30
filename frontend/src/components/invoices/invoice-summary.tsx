"use client";

import { useMemo, useState, useEffect, useRef } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { formatCurrency } from "@/lib/format";
import type { LineItem } from "./line-items-editor";

interface Customer {
  id: string;
  first_name: string;
  last_name: string;
  company_name: string | null;
}

interface InvoiceSummaryProps {
  customerId: string;
  onCustomerChange: (id: string) => void;
  subject: string;
  onSubjectChange: (v: string) => void;
  issueDate: string;
  onIssueDateChange: (v: string) => void;
  dueDate: string;
  onDueDateChange: (v: string) => void;
  taxRate: number;
  onTaxRateChange: (v: number) => void;
  discount: number;
  onDiscountChange: (v: number) => void;
  notes: string;
  onNotesChange: (v: string) => void;
  lineItems: LineItem[];
}

function CustomerSearch({
  value,
  onChange,
}: {
  value: string;
  onChange: (id: string) => void;
}) {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [search, setSearch] = useState("");
  const [open, setOpen] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const wrapperRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (loaded) return;
    api
      .get<{ items: Customer[] }>("/v1/customers?limit=200")
      .then((d) => setCustomers(d.items))
      .catch(() => {})
      .finally(() => setLoaded(true));
  }, [loaded]);

  // Set search text when value changes externally (e.g., AI draft)
  useEffect(() => {
    if (value && customers.length > 0) {
      const c = customers.find((c) => c.id === value);
      if (c) {
        const label = c.company_name
          ? `${c.first_name} ${c.last_name} (${c.company_name})`
          : `${c.first_name} ${c.last_name}`;
        setSearch(label);
      }
    }
  }, [value, customers]);

  // Close dropdown on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const filtered = useMemo(() => {
    if (!search.trim()) return customers;
    const q = search.toLowerCase();
    return customers.filter(
      (c) =>
        c.first_name.toLowerCase().includes(q) ||
        c.last_name.toLowerCase().includes(q) ||
        (c.company_name && c.company_name.toLowerCase().includes(q))
    );
  }, [customers, search]);

  return (
    <div ref={wrapperRef} className="relative">
      <Input
        value={search}
        onChange={(e) => {
          setSearch(e.target.value);
          setOpen(true);
          if (!e.target.value.trim()) onChange("");
        }}
        onFocus={() => setOpen(true)}
        placeholder="Search clients..."
        className="text-sm"
      />
      {open && filtered.length > 0 && (
        <div className="absolute z-50 mt-1 w-full max-h-48 overflow-y-auto rounded-md border bg-popover shadow-md">
          {filtered.map((c) => {
            const label = c.company_name
              ? `${c.first_name} ${c.last_name} (${c.company_name})`
              : `${c.first_name} ${c.last_name}`;
            return (
              <button
                key={c.id}
                type="button"
                className={`w-full text-left px-3 py-1.5 text-sm hover:bg-accent ${c.id === value ? "bg-accent font-medium" : ""}`}
                onClick={() => {
                  onChange(c.id);
                  setSearch(label);
                  setOpen(false);
                }}
              >
                {label}
              </button>
            );
          })}
        </div>
      )}
      {open && filtered.length === 0 && search.trim() && (
        <div className="absolute z-50 mt-1 w-full rounded-md border bg-popover shadow-md p-3 text-sm text-muted-foreground">
          No clients found
        </div>
      )}
    </div>
  );
}

export function InvoiceSummary({
  customerId,
  onCustomerChange,
  subject,
  onSubjectChange,
  issueDate,
  onIssueDateChange,
  dueDate,
  onDueDateChange,
  taxRate,
  onTaxRateChange,
  discount,
  onDiscountChange,
  notes,
  onNotesChange,
  lineItems,
  section,
}: InvoiceSummaryProps & { section?: "top" | "bottom" }) {
  const subtotal = useMemo(
    () => lineItems.reduce((sum, li) => sum + li.quantity * li.unit_price, 0),
    [lineItems]
  );

  const taxableAmount = useMemo(
    () =>
      lineItems
        .filter((li) => li.is_taxed)
        .reduce((sum, li) => sum + li.quantity * li.unit_price, 0),
    [lineItems]
  );

  const taxAmount = taxableAmount * (taxRate / 100);
  const total = subtotal + taxAmount - discount;

  const showTop = !section || section === "top";
  const showBottom = !section || section === "bottom";

  return (
    <div className="space-y-4">
      {/* TOP: Client + Details */}
      {showTop && (
        <>
          <Card className="shadow-sm">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm">Client</CardTitle>
            </CardHeader>
            <CardContent>
              <CustomerSearch value={customerId} onChange={onCustomerChange} />
            </CardContent>
          </Card>

          <Card className="shadow-sm">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm">Details</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">Subject</Label>
                <Input
                  value={subject}
                  onChange={(e) => onSubjectChange(e.target.value)}
                  placeholder="e.g., Monthly pool service"
                  className="text-sm"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label className="text-xs text-muted-foreground">Issue Date</Label>
                  <Input type="date" value={issueDate} onChange={(e) => onIssueDateChange(e.target.value)} className="text-sm" />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs text-muted-foreground">Due Date</Label>
                  <Input type="date" value={dueDate} onChange={(e) => onDueDateChange(e.target.value)} className="text-sm" />
                </div>
              </div>
            </CardContent>
          </Card>
        </>
      )}

      {/* BOTTOM: Tax/Discount + Notes + Totals */}
      {showBottom && (
        <>
          <Card className="shadow-sm">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm">Tax & Discount</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label className="text-xs text-muted-foreground">Tax Rate (%)</Label>
                  <Input type="number" min="0" step="0.01" value={taxRate || ""} onChange={(e) => onTaxRateChange(parseFloat(e.target.value) || 0)} className="text-sm" />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs text-muted-foreground">Discount ($)</Label>
                  <Input type="number" min="0" step="0.01" value={discount || ""} onChange={(e) => onDiscountChange(parseFloat(e.target.value) || 0)} className="text-sm" />
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="shadow-sm">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm">Notes</CardTitle>
            </CardHeader>
            <CardContent>
              <Textarea value={notes} onChange={(e) => onNotesChange(e.target.value)} placeholder="Additional notes for the client..." rows={3} className="text-sm" />
            </CardContent>
          </Card>

          <Card className="shadow-sm">
            <CardContent className="space-y-2 text-sm py-4">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Subtotal</span>
                <span>{formatCurrency(subtotal)}</span>
              </div>
              {taxRate > 0 && (
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Tax ({taxRate}%)</span>
                  <span>{formatCurrency(taxAmount)}</span>
                </div>
              )}
              {discount > 0 && (
                <div className="flex justify-between text-red-600">
                  <span>Discount</span>
                  <span>-{formatCurrency(discount)}</span>
                </div>
              )}
              <div className="flex justify-between font-bold border-t pt-2 text-base">
                <span>Total</span>
                <span>{formatCurrency(Math.max(0, total))}</span>
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
