"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Checkbox } from "@/components/ui/checkbox";
import { toast } from "sonner";
import { Loader2, UserPlus, X } from "lucide-react";

interface ContactPromptData {
  show_prompt: boolean;
  mode: "modal" | "banner";
  sender_email: string;
  suggested_customer_id: string | null;
  suggested_customer_name: string | null;
  pre_populated: {
    first_name: string;
    last_name: string;
    email: string;
    phone: string | null;
    role: string;
  };
}

interface ClientSearchResult {
  customer_id: string;
  customer_name: string;
  property_address: string;
  property_name: string | null;
}

export function ContactLearningPrompt({
  threadId,
  onContactSaved,
}: {
  threadId: string;
  onContactSaved: () => void;
}) {
  const [prompt, setPrompt] = useState<ContactPromptData | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [bannerDismissed, setBannerDismissed] = useState(false);
  const [saving, setSaving] = useState(false);

  // Form state
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [role, setRole] = useState("other");
  const [receivesEstimates, setReceivesEstimates] = useState(false);
  const [receivesInvoices, setReceivesInvoices] = useState(false);
  const [receivesServiceUpdates, setReceivesServiceUpdates] = useState(true);
  const [customerId, setCustomerId] = useState("");
  const [customerName, setCustomerName] = useState("");

  // Client search
  const [clientQuery, setClientQuery] = useState("");
  const [clientResults, setClientResults] = useState<ClientSearchResult[]>([]);
  const [showClientResults, setShowClientResults] = useState(false);

  useEffect(() => {
    api.get<ContactPromptData>(`/v1/admin/agent-threads/${threadId}/contact-prompt`)
      .then((data) => {
        if (!data.show_prompt) return;
        setPrompt(data);
        setFirstName(data.pre_populated.first_name);
        setLastName(data.pre_populated.last_name);
        setEmail(data.pre_populated.email);
        setPhone(data.pre_populated.phone || "");
        setRole(data.pre_populated.role);
        setCustomerId(data.suggested_customer_id || "");
        setCustomerName(data.suggested_customer_name || "");
        setClientQuery(data.suggested_customer_name || "");
        if (data.mode === "modal") {
          setShowModal(true);
        }
      })
      .catch(() => {});
  }, [threadId]);

  // Client search debounce
  useEffect(() => {
    if (clientQuery.length < 2) {
      setClientResults([]);
      return;
    }
    const timer = setTimeout(async () => {
      try {
        const data = await api.get<ClientSearchResult[]>(
          `/v1/admin/client-search?q=${encodeURIComponent(clientQuery)}`
        );
        setClientResults(data);
        setShowClientResults(true);
      } catch {
        setClientResults([]);
      }
    }, 250);
    return () => clearTimeout(timer);
  }, [clientQuery]);

  const handleSave = async () => {
    if (!customerId) {
      toast.error("Please select a client");
      return;
    }
    setSaving(true);
    try {
      const result = await api.post<{ contact_id: string; customer_changed: boolean; customer_name: string }>(
        `/v1/admin/agent-threads/${threadId}/save-contact`,
        {
          customer_id: customerId,
          first_name: firstName || null,
          last_name: lastName || null,
          email,
          phone: phone || null,
          role,
          receives_estimates: receivesEstimates,
          receives_invoices: receivesInvoices,
          receives_service_updates: receivesServiceUpdates,
        }
      );
      toast.success(
        result.customer_changed
          ? `Contact saved & thread reassigned to ${result.customer_name}`
          : "Contact saved"
      );
      setShowModal(false);
      setPrompt(null);
      onContactSaved();
    } catch (err: unknown) {
      const detail = (err as { detail?: string })?.detail || "Failed to save contact";
      toast.error(detail);
    } finally {
      setSaving(false);
    }
  };

  const handleDismiss = async () => {
    if (!prompt) return;
    try {
      await api.post("/v1/admin/agent-threads/dismiss-contact-prompt", {
        sender_email: prompt.sender_email,
      });
    } catch {}
    setShowModal(false);
    setBannerDismissed(true);
    setPrompt(null);
  };

  if (!prompt || bannerDismissed) return null;

  // Banner mode — subtle, non-blocking
  if (prompt.mode === "banner" && !showModal) {
    return (
      <div className="flex items-center gap-2 px-3 py-2 bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 rounded-md text-sm">
        <UserPlus className="h-3.5 w-3.5 text-amber-600 shrink-0" />
        <span className="text-amber-800 dark:text-amber-200">
          Unknown sender: <span className="font-medium">{prompt.sender_email}</span>
        </span>
        <Button
          variant="ghost"
          size="sm"
          className="ml-auto h-6 text-xs text-amber-700 hover:text-amber-900"
          onClick={() => setShowModal(true)}
        >
          Add to contacts
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="h-5 w-5 text-muted-foreground hover:text-destructive"
          onClick={handleDismiss}
        >
          <X className="h-3 w-3" />
        </Button>
      </div>
    );
  }

  // Modal
  const modalContent = (
    <DialogContent className="sm:max-w-md">
      <DialogHeader>
        <DialogTitle>Add Contact</DialogTitle>
        <DialogDescription>
          <span className="font-medium">{prompt.sender_email}</span> was not found in any client profile. Save them as a contact to improve future email matching.
        </DialogDescription>
      </DialogHeader>

      <div className="space-y-3">
        {/* Client selector */}
        <div>
          <Label className="text-xs font-medium">Client</Label>
          <div className="relative mt-1">
            <Input
              value={clientQuery}
              onChange={(e) => {
                setClientQuery(e.target.value);
                if (customerId) {
                  setCustomerId("");
                  setCustomerName("");
                }
              }}
              onFocus={() => clientResults.length > 0 && setShowClientResults(true)}
              placeholder="Search clients..."
              className="h-8 text-sm"
            />
            {showClientResults && clientResults.length > 0 && (
              <>
                <div className="fixed inset-0 z-40" onClick={() => setShowClientResults(false)} />
                <div className="absolute top-full left-0 right-0 z-50 mt-1 max-h-40 overflow-y-auto rounded-md border bg-background shadow-lg">
                  {clientResults.map((r) => (
                    <button
                      key={r.customer_id}
                      type="button"
                      className="w-full px-3 py-2 text-left hover:bg-muted/50 text-sm"
                      onClick={() => {
                        setCustomerId(r.customer_id);
                        setCustomerName(r.customer_name);
                        setClientQuery(r.customer_name);
                        setShowClientResults(false);
                      }}
                    >
                      <span className="font-medium">{r.customer_name}</span>
                      <span className="text-xs text-muted-foreground block">{r.property_address}</span>
                    </button>
                  ))}
                </div>
              </>
            )}
          </div>
          {customerId && customerName && (
            <p className="text-xs text-muted-foreground mt-1">Selected: {customerName}</p>
          )}
        </div>

        {/* Name fields */}
        <div className="grid grid-cols-2 gap-2">
          <div>
            <Label className="text-xs font-medium">First Name</Label>
            <Input value={firstName} onChange={(e) => setFirstName(e.target.value)} className="h-8 text-sm mt-1" />
          </div>
          <div>
            <Label className="text-xs font-medium">Last Name</Label>
            <Input value={lastName} onChange={(e) => setLastName(e.target.value)} className="h-8 text-sm mt-1" />
          </div>
        </div>

        {/* Email (read-only) */}
        <div>
          <Label className="text-xs font-medium">Email</Label>
          <Input value={email} readOnly className="h-8 text-sm mt-1 bg-muted/50" />
        </div>

        {/* Phone */}
        <div>
          <Label className="text-xs font-medium">Phone</Label>
          <Input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="(555) 123-4567" className="h-8 text-sm mt-1" />
        </div>

        {/* Role */}
        <div>
          <Label className="text-xs font-medium">Role</Label>
          <select
            value={role}
            onChange={(e) => setRole(e.target.value)}
            className="mt-1 h-8 w-full rounded-md border border-input bg-background px-3 text-sm ring-offset-background focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
          >
            <option value="property_manager">Property Manager</option>
            <option value="regional_manager">Regional Manager</option>
            <option value="billing">Billing</option>
            <option value="maintenance">Maintenance</option>
            <option value="other">Other</option>
          </select>
        </div>

        {/* Email preferences */}
        <div className="space-y-2">
          <Label className="text-xs font-medium">Receives</Label>
          <div className="flex flex-wrap gap-4">
            <label className="flex items-center gap-1.5 text-xs">
              <Checkbox checked={receivesServiceUpdates} onCheckedChange={(v) => setReceivesServiceUpdates(!!v)} />
              Service updates
            </label>
            <label className="flex items-center gap-1.5 text-xs">
              <Checkbox checked={receivesEstimates} onCheckedChange={(v) => setReceivesEstimates(!!v)} />
              Estimates
            </label>
            <label className="flex items-center gap-1.5 text-xs">
              <Checkbox checked={receivesInvoices} onCheckedChange={(v) => setReceivesInvoices(!!v)} />
              Invoices
            </label>
          </div>
        </div>
      </div>

      <DialogFooter className="gap-2 sm:gap-0">
        <Button variant="ghost" size="sm" onClick={handleDismiss}>
          Skip
        </Button>
        <Button size="sm" onClick={handleSave} disabled={saving || !customerId}>
          {saving && <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />}
          Save Contact
        </Button>
      </DialogFooter>
    </DialogContent>
  );

  return (
    <Dialog open={showModal} onOpenChange={(open) => { if (!open) handleDismiss(); }}>
      {modalContent}
    </Dialog>
  );
}
