"use client";

import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Loader2, Save, Plus, Pencil, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { FeatureSettingsSheet } from "@/components/ui/feature-settings-sheet";

interface ChargeTemplate {
  id: string;
  name: string;
  default_amount: number;
  category: string;
  is_taxable: boolean;
  requires_approval: boolean;
  sort_order: number;
}

interface Thresholds {
  auto_approve_threshold: number;
  separate_invoice_threshold: number;
  require_photo_threshold: number;
}

interface ChargeSettingsSheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ChargeSettingsSheet({ open, onOpenChange }: ChargeSettingsSheetProps) {
  return (
    <FeatureSettingsSheet
      title="Charge Settings"
      description="Configure charge templates, thresholds, and approval rules."
      open={open}
      onOpenChange={onOpenChange}
    >
      <ChargeSettingsContent />
    </FeatureSettingsSheet>
  );
}

function ChargeSettingsContent() {
  const [templates, setTemplates] = useState<ChargeTemplate[]>([]);
  const [thresholds, setThresholds] = useState<Thresholds | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<Partial<ChargeTemplate>>({});
  const [addMode, setAddMode] = useState(false);
  const [addForm, setAddForm] = useState({ name: "", default_amount: "", category: "other", requires_approval: false });
  const [thresholdForm, setThresholdForm] = useState<Thresholds>({ auto_approve_threshold: 75, separate_invoice_threshold: 200, require_photo_threshold: 50 });
  const [thresholdSaving, setThresholdSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      const [tmpls, thresh] = await Promise.all([
        api.get<ChargeTemplate[]>("/v1/charge-templates"),
        api.get<Thresholds>("/v1/charge-settings"),
      ]);
      setTemplates(tmpls);
      setThresholds(thresh);
      setThresholdForm(thresh);
    } catch {
      toast.error("Failed to load charge settings");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const saveTemplate = async (id: string) => {
    setSaving(true);
    try {
      await api.put(`/v1/charge-templates/${id}`, editForm);
      toast.success("Template updated");
      setEditingId(null);
      load();
    } catch {
      toast.error("Failed to save");
    } finally {
      setSaving(false);
    }
  };

  const addTemplate = async () => {
    if (!addForm.name || !addForm.default_amount) return;
    setSaving(true);
    try {
      await api.post("/v1/charge-templates", {
        name: addForm.name,
        default_amount: parseFloat(addForm.default_amount),
        category: addForm.category,
        requires_approval: addForm.requires_approval,
      });
      toast.success("Template created");
      setAddMode(false);
      setAddForm({ name: "", default_amount: "", category: "other", requires_approval: false });
      load();
    } catch {
      toast.error("Failed to create");
    } finally {
      setSaving(false);
    }
  };

  const deleteTemplate = async (id: string) => {
    try {
      await api.delete(`/v1/charge-templates/${id}`);
      toast.success("Template removed");
      load();
    } catch {
      toast.error("Failed to delete");
    }
  };

  const saveThresholds = async () => {
    setThresholdSaving(true);
    try {
      const updated = await api.put<Thresholds>("/v1/charge-settings", thresholdForm);
      setThresholds(updated);
      toast.success("Thresholds saved");
    } catch {
      toast.error("Failed to save thresholds");
    } finally {
      setThresholdSaving(false);
    }
  };

  if (loading) {
    return <div className="flex justify-center py-8"><Loader2 className="h-5 w-5 animate-spin" /></div>;
  }

  return (
    <div className="space-y-6">
      {/* Thresholds */}
      <Card className="shadow-sm">
        <CardHeader>
          <CardTitle className="text-base">Charge Thresholds</CardTitle>
          <CardDescription>Control auto-approval, photo requirements, and separate invoicing.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 gap-4">
            <div className="space-y-1">
              <Label className="text-xs">Auto-Approve Below</Label>
              <div className="flex items-center gap-1.5">
                <span className="text-sm text-muted-foreground">$</span>
                <Input
                  type="number"
                  step="5"
                  className="h-8 text-sm max-w-[120px]"
                  value={thresholdForm.auto_approve_threshold}
                  onChange={(e) => setThresholdForm({ ...thresholdForm, auto_approve_threshold: parseFloat(e.target.value) || 0 })}
                />
              </div>
              <p className="text-[10px] text-muted-foreground">Charges below this amount skip approval</p>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Require Photo Above</Label>
              <div className="flex items-center gap-1.5">
                <span className="text-sm text-muted-foreground">$</span>
                <Input
                  type="number"
                  step="5"
                  className="h-8 text-sm max-w-[120px]"
                  value={thresholdForm.require_photo_threshold}
                  onChange={(e) => setThresholdForm({ ...thresholdForm, require_photo_threshold: parseFloat(e.target.value) || 0 })}
                />
              </div>
              <p className="text-[10px] text-muted-foreground">Photo evidence recommended above this</p>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Separate Invoice Above</Label>
              <div className="flex items-center gap-1.5">
                <span className="text-sm text-muted-foreground">$</span>
                <Input
                  type="number"
                  step="10"
                  className="h-8 text-sm max-w-[120px]"
                  value={thresholdForm.separate_invoice_threshold}
                  onChange={(e) => setThresholdForm({ ...thresholdForm, separate_invoice_threshold: parseFloat(e.target.value) || 0 })}
                />
              </div>
              <p className="text-[10px] text-muted-foreground">Large charges become separate estimates</p>
            </div>
          </div>
          <Button onClick={saveThresholds} disabled={thresholdSaving} size="sm" className="mt-4">
            {thresholdSaving ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" /> : <Save className="h-3.5 w-3.5 mr-1.5" />}
            Save Thresholds
          </Button>
        </CardContent>
      </Card>

      {/* Templates */}
      <Card className="shadow-sm">
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-base">Charge Templates</CardTitle>
              <CardDescription>Predefined charge types techs can select in the field.</CardDescription>
            </div>
            <Button variant="outline" size="sm" onClick={() => setAddMode(true)}>
              <Plus className="h-3.5 w-3.5 mr-1.5" />
              Add
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {addMode && (
              <div className="border rounded-lg p-3 space-y-3 bg-muted/30">
                <div className="space-y-3">
                  <Input placeholder="Name" className="h-8 text-sm" value={addForm.name} onChange={(e) => setAddForm({ ...addForm, name: e.target.value })} />
                  <div className="flex items-center gap-1">
                    <span className="text-sm text-muted-foreground">$</span>
                    <Input type="number" placeholder="Amount" className="h-8 text-sm" value={addForm.default_amount} onChange={(e) => setAddForm({ ...addForm, default_amount: e.target.value })} />
                  </div>
                  <Select value={addForm.category} onValueChange={(v) => setAddForm({ ...addForm, category: v })}>
                    <SelectTrigger className="h-8 text-sm"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="time">Time</SelectItem>
                      <SelectItem value="chemical">Chemical</SelectItem>
                      <SelectItem value="material">Material</SelectItem>
                      <SelectItem value="other">Other</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="flex items-center justify-between">
                  <label className="flex items-center gap-2 text-xs">
                    <Switch
                      checked={addForm.requires_approval}
                      onCheckedChange={(v) => setAddForm({ ...addForm, requires_approval: v })}
                      className="h-4 w-7"
                    />
                    Always requires approval
                  </label>
                  <div className="flex gap-2">
                    <Button size="sm" onClick={addTemplate} disabled={saving || !addForm.name || !addForm.default_amount}>
                      {saving ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : null}Save
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => setAddMode(false)}>Cancel</Button>
                  </div>
                </div>
              </div>
            )}

            {templates.map((tmpl) => (
              <div key={tmpl.id} className="border rounded-lg p-3">
                {editingId === tmpl.id ? (
                  <div className="space-y-3">
                    <div className="space-y-3">
                      <Input className="h-8 text-sm" value={editForm.name || ""} onChange={(e) => setEditForm({ ...editForm, name: e.target.value })} />
                      <div className="flex items-center gap-1">
                        <span className="text-sm text-muted-foreground">$</span>
                        <Input type="number" className="h-8 text-sm" value={editForm.default_amount || ""} onChange={(e) => setEditForm({ ...editForm, default_amount: parseFloat(e.target.value) || 0 })} />
                      </div>
                      <Select value={editForm.category || "other"} onValueChange={(v) => setEditForm({ ...editForm, category: v })}>
                        <SelectTrigger className="h-8 text-sm"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="time">Time</SelectItem>
                          <SelectItem value="chemical">Chemical</SelectItem>
                          <SelectItem value="material">Material</SelectItem>
                          <SelectItem value="other">Other</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="flex items-center justify-between">
                      <label className="flex items-center gap-2 text-xs">
                        <Switch
                          checked={!!editForm.requires_approval}
                          onCheckedChange={(v) => setEditForm({ ...editForm, requires_approval: v })}
                          className="h-4 w-7"
                        />
                        Always requires approval
                      </label>
                      <div className="flex gap-2">
                        <Button size="sm" onClick={() => saveTemplate(tmpl.id)} disabled={saving}>
                          {saving ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : null}Save
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => setEditingId(null)}>Cancel</Button>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-sm font-medium">{tmpl.name}</span>
                        <span className="text-sm font-semibold">${tmpl.default_amount.toFixed(0)}</span>
                        <Badge variant="secondary" className="text-[10px]">{tmpl.category}</Badge>
                        {tmpl.requires_approval && (
                          <Badge variant="outline" className="text-[10px] border-amber-400 text-amber-600">Approval</Badge>
                        )}
                      </div>
                    </div>
                    <div className="flex gap-1">
                      <Button variant="ghost" size="icon" onClick={() => { setEditingId(tmpl.id); setEditForm({ ...tmpl }); }}>
                        <Pencil className="h-3.5 w-3.5" />
                      </Button>
                      <Button variant="ghost" size="icon" onClick={() => deleteTemplate(tmpl.id)} className="text-destructive">
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
