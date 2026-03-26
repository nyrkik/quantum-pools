"use client";

import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import {
  Loader2,
  Plus,
  Pencil,
  Trash2,
  ExternalLink,
  Search,
  Check,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";

interface Vendor {
  id: string;
  name: string;
  provider_type: string;
  portal_url: string | null;
  search_url_template: string | null;
  account_number: string | null;
  is_active: boolean;
  sort_order: number;
}

interface VendorForm {
  name: string;
  provider_type: string;
  portal_url: string;
  search_url_template: string;
  account_number: string;
}

const EMPTY_FORM: VendorForm = {
  name: "",
  provider_type: "generic",
  portal_url: "",
  search_url_template: "",
  account_number: "",
};

export function VendorsSection({ editMode }: { editMode: boolean }) {
  const [vendors, setVendors] = useState<Vendor[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<VendorForm>(EMPTY_FORM);
  const [addMode, setAddMode] = useState(false);
  const [addForm, setAddForm] = useState<VendorForm>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [testQuery, setTestQuery] = useState("");

  const load = useCallback(async () => {
    try {
      const data = await api.get<Vendor[]>("/v1/vendors");
      setVendors(data);
    } catch {
      toast.error("Failed to load vendors");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleAdd = async () => {
    if (!addForm.name.trim()) return;
    setSaving(true);
    try {
      await api.post("/v1/vendors", {
        name: addForm.name,
        provider_type: addForm.provider_type || "generic",
        portal_url: addForm.portal_url || null,
        search_url_template: addForm.search_url_template || null,
        account_number: addForm.account_number || null,
      });
      toast.success("Vendor added");
      setAddMode(false);
      setAddForm(EMPTY_FORM);
      load();
    } catch {
      toast.error("Failed to add vendor");
    } finally {
      setSaving(false);
    }
  };

  const handleEdit = (v: Vendor) => {
    setEditingId(v.id);
    setEditForm({
      name: v.name,
      provider_type: v.provider_type,
      portal_url: v.portal_url || "",
      search_url_template: v.search_url_template || "",
      account_number: v.account_number || "",
    });
  };

  const handleSave = async () => {
    if (!editingId || !editForm.name.trim()) return;
    setSaving(true);
    try {
      await api.put(`/v1/vendors/${editingId}`, {
        name: editForm.name,
        provider_type: editForm.provider_type || "generic",
        portal_url: editForm.portal_url || null,
        search_url_template: editForm.search_url_template || null,
        account_number: editForm.account_number || null,
      });
      toast.success("Vendor updated");
      setEditingId(null);
      load();
    } catch {
      toast.error("Failed to update vendor");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await api.delete(`/v1/vendors/${id}`);
      toast.success("Vendor removed");
      load();
    } catch {
      toast.error("Failed to remove vendor");
    }
  };

  const handleTestSearch = async (vendor: Vendor) => {
    const q = testQuery.trim() || "pool pump";
    try {
      const result = await api.get<{ url: string }>(`/v1/vendors/${vendor.id}/search-url?q=${encodeURIComponent(q)}`);
      window.open(result.url, "_blank");
    } catch {
      toast.error("No search template configured");
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center py-12">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <Card className="shadow-sm">
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-base">Vendors</CardTitle>
            <CardDescription>Configure your parts suppliers and search portals.</CardDescription>
          </div>
          {editMode && !addMode && (
            <Button variant="outline" size="sm" onClick={() => setAddMode(true)}>
              <Plus className="h-3.5 w-3.5 mr-1.5" /> Add Vendor
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Add form */}
        {addMode && (
          <div className="border rounded-lg p-4 bg-muted/50 space-y-3">
            <VendorFormFields form={addForm} onChange={setAddForm} />
            <div className="flex gap-2">
              <Button size="sm" onClick={handleAdd} disabled={saving || !addForm.name.trim()}>
                {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" /> : <Check className="h-3.5 w-3.5 mr-1.5" />}
                Add
              </Button>
              <Button variant="ghost" size="sm" onClick={() => { setAddMode(false); setAddForm(EMPTY_FORM); }}>
                Cancel
              </Button>
            </div>
          </div>
        )}

        {/* Vendor list */}
        {vendors.length === 0 && !addMode && (
          <p className="text-sm text-muted-foreground py-4 text-center">No vendors configured yet.</p>
        )}

        {vendors.map((v) => (
          <div key={v.id} className={`border rounded-lg p-4 ${editingId === v.id ? "bg-muted/50 border-l-4 border-l-primary" : ""}`}>
            {editingId === v.id ? (
              <div className="space-y-3">
                <VendorFormFields form={editForm} onChange={setEditForm} />
                <div className="flex gap-2">
                  <Button size="sm" onClick={handleSave} disabled={saving || !editForm.name.trim()}>
                    {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" /> : <Check className="h-3.5 w-3.5 mr-1.5" />}
                    Save
                  </Button>
                  <Button variant="ghost" size="sm" onClick={() => setEditingId(null)}>
                    Cancel
                  </Button>
                </div>
              </div>
            ) : (
              <div className="flex items-start justify-between">
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-sm">{v.name}</span>
                    <span className="text-xs text-muted-foreground bg-muted px-1.5 py-0.5 rounded">{v.provider_type}</span>
                  </div>
                  {v.account_number && (
                    <p className="text-xs text-muted-foreground">Account: {v.account_number}</p>
                  )}
                  <div className="flex items-center gap-2 pt-1">
                    {v.portal_url && (
                      <Button variant="outline" size="sm" className="h-7 text-xs" asChild>
                        <a href={v.portal_url} target="_blank" rel="noopener noreferrer">
                          <ExternalLink className="h-3 w-3 mr-1" /> Open Portal
                        </a>
                      </Button>
                    )}
                    {v.search_url_template && (
                      <div className="flex items-center gap-1">
                        <Input
                          value={testQuery}
                          onChange={(e) => setTestQuery(e.target.value)}
                          placeholder="pool pump"
                          className="h-7 text-xs w-28"
                        />
                        <Button variant="outline" size="sm" className="h-7 text-xs" onClick={() => handleTestSearch(v)}>
                          <Search className="h-3 w-3 mr-1" /> Search
                        </Button>
                      </div>
                    )}
                  </div>
                </div>
                {editMode && (
                  <div className="flex items-center gap-1">
                    <Button variant="ghost" size="icon" onClick={() => handleEdit(v)}>
                      <Pencil className="h-3.5 w-3.5" />
                    </Button>
                    <AlertDialog>
                      <AlertDialogTrigger asChild>
                        <Button variant="ghost" size="icon">
                          <Trash2 className="h-3.5 w-3.5 text-destructive" />
                        </Button>
                      </AlertDialogTrigger>
                      <AlertDialogContent>
                        <AlertDialogHeader>
                          <AlertDialogTitle>Remove {v.name}?</AlertDialogTitle>
                          <AlertDialogDescription>This vendor will be deactivated. Existing purchase records will not be affected.</AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                          <AlertDialogCancel>Cancel</AlertDialogCancel>
                          <AlertDialogAction onClick={() => handleDelete(v.id)}>Remove</AlertDialogAction>
                        </AlertDialogFooter>
                      </AlertDialogContent>
                    </AlertDialog>
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function VendorFormFields({ form, onChange }: { form: VendorForm; onChange: (f: VendorForm) => void }) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
      <div className="space-y-1">
        <Label className="text-xs">Name</Label>
        <Input
          value={form.name}
          onChange={(e) => onChange({ ...form, name: e.target.value })}
          placeholder="SCP Distributors"
          className="h-8 text-sm"
        />
      </div>
      <div className="space-y-1">
        <Label className="text-xs">Type</Label>
        <Input
          value={form.provider_type}
          onChange={(e) => onChange({ ...form, provider_type: e.target.value })}
          placeholder="scp, pentair, generic"
          className="h-8 text-sm"
        />
      </div>
      <div className="space-y-1">
        <Label className="text-xs">Portal URL</Label>
        <Input
          value={form.portal_url}
          onChange={(e) => onChange({ ...form, portal_url: e.target.value })}
          placeholder="https://www.pool360.com"
          className="h-8 text-sm"
        />
      </div>
      <div className="space-y-1">
        <Label className="text-xs">Account Number</Label>
        <Input
          value={form.account_number}
          onChange={(e) => onChange({ ...form, account_number: e.target.value })}
          placeholder="Optional"
          className="h-8 text-sm"
        />
      </div>
      <div className="sm:col-span-2 space-y-1">
        <Label className="text-xs">Search URL Template</Label>
        <Input
          value={form.search_url_template}
          onChange={(e) => onChange({ ...form, search_url_template: e.target.value })}
          placeholder="https://www.pool360.com/Catalog/Search?q={query}"
          className="h-8 text-sm"
        />
        <p className="text-[10px] text-muted-foreground">Use {"{query}"} as placeholder for search terms</p>
      </div>
    </div>
  );
}
