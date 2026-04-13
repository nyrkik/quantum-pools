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
import { Loader2, UserPlus, Tag, X } from "lucide-react";

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

const SENDER_TAGS = [
  { value: "billing", label: "Billing", description: "Payment notifications, invoices, AP/AR" },
  { value: "vendor", label: "Vendor", description: "Supply houses, equipment distributors" },
  { value: "business", label: "Business", description: "Insurance, accountant, licensing, trade orgs" },
  { value: "notification", label: "Notification", description: "System alerts, confirmations" },
  { value: "personal", label: "Personal", description: "Friends, family, non-business" },
  { value: "marketing", label: "Marketing", description: "Newsletters, promotions" },
  { value: "other", label: "Other", description: "Known sender, no specific category" },
  { value: "spam", label: "Spam", description: "Junk, unwanted" },
] as const;

export const SENDER_TAG_STYLES: Record<string, { bg: string; text: string }> = {
  client: { bg: "bg-emerald-100 dark:bg-emerald-950/40", text: "text-emerald-700 dark:text-emerald-400" },
  billing: { bg: "bg-blue-100 dark:bg-blue-950/40", text: "text-blue-700 dark:text-blue-400" },
  vendor: { bg: "bg-purple-100 dark:bg-purple-950/40", text: "text-purple-700 dark:text-purple-400" },
  business: { bg: "bg-indigo-100 dark:bg-indigo-950/40", text: "text-indigo-700 dark:text-indigo-400" },
  notification: { bg: "bg-slate-100 dark:bg-slate-800", text: "text-slate-600 dark:text-slate-400" },
  personal: { bg: "bg-green-100 dark:bg-green-950/40", text: "text-green-700 dark:text-green-400" },
  marketing: { bg: "bg-orange-100 dark:bg-orange-950/40", text: "text-orange-700 dark:text-orange-400" },
  other: { bg: "bg-gray-100 dark:bg-gray-800", text: "text-gray-600 dark:text-gray-400" },
  spam: { bg: "bg-red-100 dark:bg-red-950/40", text: "text-red-700 dark:text-red-400" },
};

type DialogMode = "choose" | "contact" | "tag";

export function ContactLearningPrompt({
  threadId,
  onContactSaved,
}: {
  threadId: string;
  onContactSaved: () => void;
}) {
  const [prompt, setPrompt] = useState<ContactPromptData | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [dialogMode, setDialogMode] = useState<DialogMode>("choose");
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

  // Tag state
  const [selectedTag, setSelectedTag] = useState<string>("notification");
  const [selectedFolderId, setSelectedFolderId] = useState<string | null>(null);
  const [folders, setFolders] = useState<{ id: string; name: string; system_key: string | null }[]>([]);

  useEffect(() => {
    api.get<{ folders: { id: string; name: string; system_key: string | null }[] }>("/v1/inbox-folders")
      .then((d) => setFolders(d.folders.filter((f) => f.system_key !== "sent" && f.system_key !== "spam")))
      .catch(() => {});
  }, []);

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

  const handleTagSender = async () => {
    if (!prompt) return;
    setSaving(true);
    try {
      await api.post("/v1/admin/agent-threads/dismiss-contact-prompt", {
        sender_email: prompt.sender_email,
        reason: selectedTag,
        folder_id: selectedFolderId,
      });
      const label = SENDER_TAGS.find((t) => t.value === selectedTag)?.label || selectedTag;
      toast.success(`Sender tagged as "${label}"`);
      setShowModal(false);
      setPrompt(null);
      onContactSaved();
    } catch {
      toast.error("Failed to tag sender");
    } finally {
      setSaving(false);
    }
  };

  const openDialog = () => {
    setDialogMode("choose");
    setShowModal(true);
  };

  if (!prompt) return null;

  return (
    <>
      <button
        onClick={openDialog}
        className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-amber-100 dark:bg-amber-950/40 text-amber-700 dark:text-amber-400 hover:bg-amber-200 dark:hover:bg-amber-950/60 transition-colors"
        title="Unknown sender — click to add as contact or tag"
      >
        <UserPlus className="h-2.5 w-2.5" />
        Unknown
      </button>

      <Dialog open={showModal} onOpenChange={(open) => { if (!open) setShowModal(false); }}>
        <DialogContent className="sm:max-w-md">
          {dialogMode === "choose" && (
            <>
              <DialogHeader>
                <DialogTitle>Identify Sender</DialogTitle>
                <DialogDescription>
                  <span className="font-medium">{prompt.sender_email}</span>
                </DialogDescription>
              </DialogHeader>
              <div className="space-y-2">
                <button
                  onClick={() => setDialogMode("contact")}
                  className="w-full flex items-center gap-3 p-3 rounded-lg border hover:bg-muted/50 transition-colors text-left"
                >
                  <UserPlus className="h-5 w-5 text-primary shrink-0" />
                  <div>
                    <p className="text-sm font-medium">Save as Client Contact</p>
                    <p className="text-xs text-muted-foreground">Link this sender to a customer profile</p>
                  </div>
                </button>
                <button
                  onClick={() => setDialogMode("tag")}
                  className="w-full flex items-center gap-3 p-3 rounded-lg border hover:bg-muted/50 transition-colors text-left"
                >
                  <Tag className="h-5 w-5 text-primary shrink-0" />
                  <div>
                    <p className="text-sm font-medium">Tag Sender</p>
                    <p className="text-xs text-muted-foreground">Mark as billing, vendor, notification, etc.</p>
                  </div>
                </button>
              </div>
            </>
          )}

          {dialogMode === "tag" && (
            <>
              <DialogHeader>
                <DialogTitle>Tag Sender</DialogTitle>
                <DialogDescription>
                  Choose a tag for <span className="font-medium">{prompt.sender_email}</span>. This applies org-wide — all users will see this tag.
                </DialogDescription>
              </DialogHeader>
              <div className="space-y-1.5">
                {SENDER_TAGS.map((tag) => {
                  const style = SENDER_TAG_STYLES[tag.value];
                  return (
                    <button
                      key={tag.value}
                      onClick={() => setSelectedTag(tag.value)}
                      className={`w-full flex items-center gap-3 p-2.5 rounded-lg border transition-colors text-left ${
                        selectedTag === tag.value ? "border-primary bg-primary/5" : "hover:bg-muted/50"
                      }`}
                    >
                      <span className={`px-2 py-0.5 rounded text-[10px] font-medium ${style.bg} ${style.text}`}>
                        {tag.label}
                      </span>
                      <span className="text-xs text-muted-foreground">{tag.description}</span>
                    </button>
                  );
                })}
              </div>
              {/* Folder routing */}
              <div className="pt-2 border-t">
                <Label className="text-xs font-medium">Move emails from this sender to:</Label>
                <select
                  value={selectedFolderId || ""}
                  onChange={(e) => setSelectedFolderId(e.target.value || null)}
                  className="mt-1 h-8 w-full rounded-md border border-input bg-background px-3 text-sm"
                >
                  <option value="">Inbox (default)</option>
                  {folders.filter((f) => f.system_key !== "inbox").map((f) => (
                    <option key={f.id} value={f.id}>{f.name}</option>
                  ))}
                </select>
                <p className="text-[10px] text-muted-foreground mt-1">
                  Existing and future emails from this sender will be moved automatically.
                </p>
              </div>
              <DialogFooter className="gap-2 sm:gap-0">
                <Button variant="ghost" size="sm" onClick={() => setDialogMode("choose")}>
                  Back
                </Button>
                <Button size="sm" onClick={handleTagSender} disabled={saving}>
                  {saving && <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />}
                  Save Tag
                </Button>
              </DialogFooter>
            </>
          )}

          {dialogMode === "contact" && (
            <>
              <DialogHeader>
                <DialogTitle>Add Contact</DialogTitle>
                <DialogDescription>
                  Link <span className="font-medium">{prompt.sender_email}</span> to a client profile.
                </DialogDescription>
              </DialogHeader>

              <div className="space-y-3">
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

                <div>
                  <Label className="text-xs font-medium">Email</Label>
                  <Input value={email} readOnly className="h-8 text-sm mt-1 bg-muted/50" />
                </div>

                <div>
                  <Label className="text-xs font-medium">Phone</Label>
                  <Input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="(555) 123-4567" className="h-8 text-sm mt-1" />
                </div>

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
                <Button variant="ghost" size="sm" onClick={() => setDialogMode("choose")}>
                  Back
                </Button>
                <Button size="sm" onClick={handleSave} disabled={saving || !customerId}>
                  {saving && <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />}
                  Save Contact
                </Button>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
