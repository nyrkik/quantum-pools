"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { api } from "@/lib/api";
import { useCompose } from "./compose-provider";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import {
  Minus,
  X,
  Send,
  Sparkles,
  Loader2,
  ChevronDown,
  ChevronUp,
  User,
  Search,
} from "lucide-react";

// --- Types ---

interface CustomerResult {
  id: string;
  first_name: string;
  last_name: string;
  company_name?: string;
  customer_type: string;
  email?: string;
  display_name?: string;
}

interface CustomerContext {
  id: string;
  name: string;
  email: string | null;
  phone: string | null;
  company: string | null;
  type: string;
  balance: number;
  properties: { id: string; address: string; name: string | null }[];
  water_features: { name: string; type: string; gallons: number | null }[];
  recent_threads: { subject: string | null; status: string; last_at: string | null }[];
  open_invoices: { number: string; total: number; due_date: string; status: string }[];
  open_jobs: { type: string; description: string; status: string }[];
  last_visit: string | null;
}

// --- Component ---

export function ComposeEmail() {
  const { isOpen, isMinimized, options, closeCompose, toggleMinimize } = useCompose();

  const [to, setTo] = useState("");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [customerId, setCustomerId] = useState<string | null>(null);
  const [customerName, setCustomerName] = useState<string | null>(null);

  // Customer search
  const [customerSearch, setCustomerSearch] = useState("");
  const [customerResults, setCustomerResults] = useState<CustomerResult[]>([]);
  const [showResults, setShowResults] = useState(false);
  const [searchLoading, setSearchLoading] = useState(false);
  const searchRef = useRef<HTMLDivElement>(null);
  const searchTimeout = useRef<ReturnType<typeof setTimeout>>(undefined);

  // AI
  const [aiInstruction, setAiInstruction] = useState("");
  const [aiLoading, setAiLoading] = useState(false);
  const [showAiAssist, setShowAiAssist] = useState(false);

  // Customer context
  const [context, setContext] = useState<CustomerContext | null>(null);
  const [showContext, setShowContext] = useState(false);
  const [contextLoading, setContextLoading] = useState(false);

  // Sending
  const [sending, setSending] = useState(false);

  // Seed from options
  useEffect(() => {
    if (isOpen) {
      setTo(options.to || "");
      setSubject(options.subject || "");
      setBody(options.body || "");
      setCustomerId(options.customerId || null);
      setCustomerName(options.customerName || null);
      setAiInstruction("");
      setShowAiAssist(false);
      setContext(null);
      setShowContext(false);

      if (options.customerId) {
        loadContext(options.customerId);
      }
    }
  }, [isOpen, options]);

  // Search customers on input change
  useEffect(() => {
    if (!customerSearch || customerSearch.length < 2) {
      setCustomerResults([]);
      setShowResults(false);
      return;
    }
    clearTimeout(searchTimeout.current);
    searchTimeout.current = setTimeout(async () => {
      setSearchLoading(true);
      try {
        const data = await api.get<{ items: CustomerResult[] }>(
          `/v1/customers?search=${encodeURIComponent(customerSearch)}&limit=8`
        );
        setCustomerResults(data.items);
        setShowResults(true);
      } catch {
        setCustomerResults([]);
      } finally {
        setSearchLoading(false);
      }
    }, 300);

    return () => clearTimeout(searchTimeout.current);
  }, [customerSearch]);

  // Close dropdown on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (searchRef.current && !searchRef.current.contains(e.target as Node)) {
        setShowResults(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const loadContext = useCallback(async (custId: string) => {
    setContextLoading(true);
    try {
      const ctx = await api.get<CustomerContext>(`/v1/email/customer-context/${custId}`);
      setContext(ctx);
    } catch {
      setContext(null);
    } finally {
      setContextLoading(false);
    }
  }, []);

  const selectCustomer = (c: CustomerResult) => {
    const name = c.display_name || c.company_name || `${c.first_name} ${c.last_name}`;
    setCustomerId(c.id);
    setCustomerName(name);
    if (c.email) setTo(c.email);
    setCustomerSearch("");
    setShowResults(false);
    loadContext(c.id);
  };

  const clearCustomer = () => {
    setCustomerId(null);
    setCustomerName(null);
    setContext(null);
    setShowContext(false);
  };

  const handleGenerateDraft = async () => {
    if (!aiInstruction.trim()) return;
    setAiLoading(true);
    try {
      const result = await api.post<{ subject: string; body: string; error?: string }>("/v1/email/draft", {
        instruction: aiInstruction.trim(),
        customer_id: customerId,
        existing_body: body || undefined,
      });
      if (result.error) {
        toast.error(`AI draft failed: ${result.error}`);
      } else {
        if (result.subject && !subject) setSubject(result.subject);
        if (result.body) setBody(result.body);
        setAiInstruction("");
        setShowAiAssist(false);
      }
    } catch (e: unknown) {
      const msg = (e as { message?: string })?.message || "Failed to generate draft";
      toast.error(msg);
    } finally {
      setAiLoading(false);
    }
  };

  const handleSend = async () => {
    if (!to.trim()) { toast.error("Recipient email is required"); return; }
    if (!subject.trim()) { toast.error("Subject is required"); return; }
    if (!body.trim()) { toast.error("Email body is required"); return; }

    setSending(true);
    try {
      await api.post("/v1/email/compose", {
        to: to.trim(),
        subject: subject.trim(),
        body: body.trim(),
        customer_id: customerId,
        job_id: options.jobId || undefined,
      });

      // Log AI draft correction if the user edited the draft
      if (options.originalDraft && (body.trim() !== options.originalDraft || subject.trim() !== (options.originalSubject || ""))) {
        api.post("/v1/email/draft-correction", {
          original_subject: options.originalSubject || "",
          original_body: options.originalDraft,
          edited_subject: subject.trim(),
          edited_body: body.trim(),
          job_id: options.jobId,
        }).catch(() => {}); // Fire and forget
      }

      toast.success("Email sent");
      if (options.onSent) options.onSent();
      closeCompose();
    } catch (e: unknown) {
      const msg = (e as { message?: string })?.message || "Failed to send email";
      toast.error(msg);
    } finally {
      setSending(false);
    }
  };

  if (!isOpen) return null;

  // Minimized bar
  if (isMinimized) {
    return (
      <div className="fixed bottom-0 right-4 z-[200] w-72 sm:w-80" style={{ pointerEvents: "auto" }}>
        <button
          type="button"
          onClick={toggleMinimize}
          className="flex w-full items-center justify-between rounded-t-lg bg-primary px-4 py-2.5 text-primary-foreground shadow-lg"
        >
          <span className="text-sm font-medium truncate">
            {subject || "New Email"}
          </span>
          <div className="flex items-center gap-1">
            <ChevronUp className="h-4 w-4" />
            <X
              className="h-4 w-4 hover:text-destructive"
              onClick={(e) => { e.stopPropagation(); closeCompose(); }}
            />
          </div>
        </button>
      </div>
    );
  }

  // Full compose window
  return (
    <div className="fixed bottom-0 right-4 z-[200] flex w-[calc(100vw-2rem)] flex-col rounded-t-lg border bg-background shadow-2xl sm:w-[480px] sm:right-6 max-h-[85vh]" style={{ pointerEvents: "auto" }}>
      {/* Header */}
      <div className="flex items-center justify-between rounded-t-lg bg-primary px-4 py-2.5 text-primary-foreground">
        <span className="text-sm font-medium">New Email</span>
        <div className="flex items-center gap-1">
          <button type="button" onClick={toggleMinimize} className="rounded p-0.5 hover:bg-primary-foreground/20">
            <Minus className="h-4 w-4" />
          </button>
          <button type="button" onClick={closeCompose} className="rounded p-0.5 hover:bg-primary-foreground/20">
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      <div className="flex flex-1 flex-col overflow-y-auto p-3 gap-2.5">
        {/* From field (shown when replying from a specific address) */}
        {options.fromAddress && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <span className="font-medium w-8">From</span>
            <span className="bg-muted px-2 py-0.5 rounded">{options.fromAddress}</span>
          </div>
        )}

        {/* To field with customer search */}
        <div ref={searchRef} className="relative">
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium text-muted-foreground w-8">To</span>
            {customerId && customerName ? (
              <div className="flex flex-1 items-center gap-2">
                <Badge variant="secondary" className="gap-1 text-xs">
                  <User className="h-3 w-3" />
                  {customerName}
                  <button type="button" onClick={clearCustomer} className="ml-0.5 hover:text-destructive">
                    <X className="h-3 w-3" />
                  </button>
                </Badge>
                <Input
                  type="email"
                  value={to}
                  onChange={(e) => setTo(e.target.value)}
                  className="h-8 text-sm flex-1"
                  placeholder="email@example.com"
                />
              </div>
            ) : (
              <div className="flex-1 relative">
                <Input
                  value={customerSearch || to}
                  onChange={(e) => {
                    const v = e.target.value;
                    if (v.includes("@")) {
                      setTo(v);
                      setCustomerSearch("");
                    } else {
                      setCustomerSearch(v);
                      setTo(v);
                    }
                  }}
                  className="h-8 text-sm"
                  placeholder="Search customer or type email..."
                />
                {searchLoading && (
                  <Loader2 className="absolute right-2 top-1.5 h-4 w-4 animate-spin text-muted-foreground" />
                )}
              </div>
            )}
          </div>

          {/* Customer search dropdown */}
          {showResults && customerResults.length > 0 && (
            <div className="absolute left-8 right-0 top-full z-50 mt-1 max-h-48 overflow-y-auto rounded-md border bg-popover shadow-md">
              {customerResults.map((c) => (
                <button
                  key={c.id}
                  type="button"
                  onClick={() => selectCustomer(c)}
                  className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-accent"
                >
                  <User className="h-3.5 w-3.5 text-muted-foreground flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <div className="font-medium truncate">
                      {c.display_name || c.company_name || `${c.first_name} ${c.last_name}`}
                    </div>
                    {c.email && (
                      <div className="text-xs text-muted-foreground truncate">{c.email}</div>
                    )}
                  </div>
                  <Badge variant="outline" className="text-[10px] flex-shrink-0">
                    {c.customer_type}
                  </Badge>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Subject */}
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-muted-foreground w-8">Subj</span>
          <Input
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            className="h-8 text-sm flex-1"
            placeholder="Subject"
          />
        </div>

        {/* AI context card */}
        {customerId && context && (
          <div className="rounded-md border bg-muted/30 px-3 py-2">
            <button
              type="button"
              onClick={() => setShowContext(!showContext)}
              className="flex w-full items-center justify-between text-xs text-muted-foreground"
            >
              <span className="flex items-center gap-1.5">
                <Sparkles className="h-3 w-3" />
                AI context loaded
              </span>
              {showContext ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
            </button>
            {showContext && (
              <div className="mt-2 space-y-1 text-xs text-muted-foreground">
                {context.properties.length > 0 && (
                  <p>Properties: {context.properties.map((p) => p.name || p.address).join(", ")}</p>
                )}
                {context.last_visit && <p>Last visit: {context.last_visit}</p>}
                {context.balance > 0 && <p>Balance: ${context.balance.toFixed(2)}</p>}
                {context.open_jobs.length > 0 && (
                  <p>Open jobs: {context.open_jobs.map((j) => j.description).join("; ")}</p>
                )}
                {context.open_invoices.length > 0 && (
                  <p>Open invoices: {context.open_invoices.length}</p>
                )}
                {context.water_features.length > 0 && (
                  <p>Water features: {context.water_features.map((w) => w.name).join(", ")}</p>
                )}
              </div>
            )}
          </div>
        )}
        {customerId && contextLoading && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground px-1">
            <Loader2 className="h-3 w-3 animate-spin" />
            Loading customer context...
          </div>
        )}

        {/* Body area — show AI prompt when empty, textarea when filled */}
        {!body && !showAiAssist ? (
          <div className="flex-1 flex flex-col gap-2 min-h-[180px]">
            <Textarea
              value={body}
              onChange={(e) => setBody(e.target.value)}
              className="flex-1 text-sm resize-none min-h-[100px]"
              placeholder="Start typing your email..."
            />
            <div className="rounded-md border border-dashed bg-muted/20 p-3">
              <div className="flex items-center gap-1.5 text-xs text-muted-foreground mb-2">
                <Sparkles className="h-3.5 w-3.5" />
                <span>AI Draft Assistant</span>
              </div>
              <div className="flex gap-2">
                <Input
                  value={aiInstruction}
                  onChange={(e) => setAiInstruction(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleGenerateDraft(); } }}
                  className="h-8 text-sm flex-1"
                  placeholder="Describe what you want to say..."
                  disabled={aiLoading}
                />
                <Button
                  size="sm"
                  className="h-8 gap-1"
                  onClick={handleGenerateDraft}
                  disabled={aiLoading || !aiInstruction.trim()}
                >
                  {aiLoading ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Sparkles className="h-3.5 w-3.5" />
                  )}
                  Generate
                </Button>
              </div>
            </div>
          </div>
        ) : (
          <div className="flex-1 flex flex-col gap-2 min-h-[180px]">
            <div className="relative flex-1">
              <Textarea
                value={body}
                onChange={(e) => setBody(e.target.value)}
                className="h-full min-h-[160px] text-sm resize-none"
                placeholder="Write your email..."
              />
            </div>

            {/* AI assist toggle */}
            {!showAiAssist ? (
              <Button
                variant="ghost"
                size="sm"
                className="self-start gap-1 text-xs text-muted-foreground"
                onClick={() => setShowAiAssist(true)}
              >
                <Sparkles className="h-3 w-3" />
                AI Assist
              </Button>
            ) : (
              <div className="rounded-md border bg-muted/20 p-2">
                <div className="flex gap-2">
                  <Input
                    value={aiInstruction}
                    onChange={(e) => setAiInstruction(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleGenerateDraft(); } }}
                    className="h-7 text-xs flex-1"
                    placeholder="How should AI improve this draft?"
                    disabled={aiLoading}
                    autoFocus
                  />
                  <Button
                    size="sm"
                    className="h-7 text-xs gap-1"
                    onClick={handleGenerateDraft}
                    disabled={aiLoading || !aiInstruction.trim()}
                  >
                    {aiLoading ? <Loader2 className="h-3 w-3 animate-spin" /> : <Sparkles className="h-3 w-3" />}
                    Rewrite
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 text-xs"
                    onClick={() => { setShowAiAssist(false); setAiInstruction(""); }}
                  >
                    <X className="h-3 w-3" />
                  </Button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between border-t px-3 py-2">
        <Button
          variant="ghost"
          size="sm"
          className="text-xs text-muted-foreground"
          onClick={closeCompose}
        >
          Discard
        </Button>
        <Button
          size="sm"
          className="gap-1.5"
          onClick={handleSend}
          disabled={sending || !to.trim() || !subject.trim() || !body.trim()}
        >
          {sending ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Send className="h-3.5 w-3.5" />
          )}
          Send
        </Button>
      </div>
    </div>
  );
}
