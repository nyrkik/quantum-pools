"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { toast } from "sonner";
import { Pencil, Loader2, X, MapPin } from "lucide-react";
import type { Permissions } from "@/lib/permissions";

interface Property {
  id: string;
  name: string | null;
  address: string;
  city: string;
  state: string;
  zip_code: string;
  gate_code: string | null;
  access_instructions: string | null;
  dog_on_property: boolean;
  monthly_rate: number | null;
  is_locked_to_day: boolean;
}

interface PropertySiteDetailsProps {
  property: Property;
  perms: Permissions;
  showAddress?: boolean;
  onUpdated: () => void;
}

export function PropertySiteDetails({ property, perms, showAddress, onUpdated }: PropertySiteDetailsProps) {
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({ ...property });
  const set = (field: string, value: unknown) => setForm(f => ({ ...f, [field]: value }));

  const dirty = form.name !== property.name
    || form.address !== property.address
    || form.city !== property.city
    || form.state !== property.state
    || form.zip_code !== property.zip_code
    || form.monthly_rate !== property.monthly_rate
    || form.gate_code !== property.gate_code
    || form.access_instructions !== property.access_instructions
    || form.dog_on_property !== property.dog_on_property
    || form.is_locked_to_day !== property.is_locked_to_day;

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.put(`/v1/properties/${property.id}`, {
        name: form.name || null,
        address: form.address,
        city: form.city,
        state: form.state,
        zip_code: form.zip_code,
        monthly_rate: form.monthly_rate,
        gate_code: form.gate_code || null,
        access_instructions: form.access_instructions || null,
        dog_on_property: form.dog_on_property,
        is_locked_to_day: form.is_locked_to_day,
      });
      toast.success("Property updated");
      setEditing(false);
      onUpdated();
    } catch {
      toast.error("Failed to update property");
    } finally {
      setSaving(false);
    }
  };

  const handleCancel = () => { setForm({ ...property }); setEditing(false); };

  if (editing) {
    return (
      <div className={`border rounded-lg p-3 space-y-2.5 bg-muted/30 ${dirty ? "border-l-4 border-l-amber-400" : "border-l-4 border-l-primary"}`}>
        <div className="flex items-center justify-between">
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Property Details</p>
          <div className="flex gap-1.5">
            {dirty && (
              <>
                <Button variant="default" size="sm" className="h-7 px-2.5 text-xs" onClick={handleSave} disabled={saving}>
                  {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : "Save"}
                </Button>
                <Button variant="ghost" size="sm" className="h-7 px-2 text-xs" onClick={handleCancel}>Cancel</Button>
              </>
            )}
            <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground hover:text-destructive" onClick={handleCancel}>
              <X className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">Name <span className="text-muted-foreground">(optional)</span></Label>
          <Input value={form.name ?? ""} onChange={(e) => set("name", e.target.value)} placeholder="e.g. East Campus" className="h-8 text-sm" />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">Address</Label>
          <Input value={form.address} onChange={(e) => set("address", e.target.value)} className="h-8 text-sm" />
        </div>
        <div className="grid grid-cols-3 gap-2">
          <div className="space-y-1.5">
            <Label className="text-xs">City</Label>
            <Input value={form.city} onChange={(e) => set("city", e.target.value)} className="h-8 text-sm" />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">State</Label>
            <Input value={form.state} onChange={(e) => set("state", e.target.value)} className="h-8 text-sm" />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Zip</Label>
            <Input value={form.zip_code} onChange={(e) => set("zip_code", e.target.value)} className="h-8 text-sm" />
          </div>
        </div>
        <div className="grid grid-cols-3 gap-2">
          <div className="space-y-1.5">
            <Label className="text-xs">Monthly Rate</Label>
            <Input type="number" step="0.01" value={form.monthly_rate ?? ""} onChange={(e) => set("monthly_rate", e.target.value ? parseFloat(e.target.value) : null)} placeholder="0.00" className="h-8 text-sm" />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Gate Code</Label>
            <Input value={form.gate_code ?? ""} onChange={(e) => set("gate_code", e.target.value)} className="h-8 text-sm" />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Access Instructions</Label>
            <Input value={form.access_instructions ?? ""} onChange={(e) => set("access_instructions", e.target.value)} className="h-8 text-sm" />
          </div>
        </div>
        <div className="flex flex-wrap gap-x-6 gap-y-2">
          <div className="flex items-center gap-2">
            <Switch checked={form.dog_on_property} onCheckedChange={(v) => set("dog_on_property", v)} />
            <Label className="text-xs">Dog on Property</Label>
          </div>
          <div className="flex items-center gap-2">
            <Switch checked={form.is_locked_to_day} onCheckedChange={(v) => set("is_locked_to_day", v)} />
            <Label className="text-xs">Locked to Day</Label>
          </div>
        </div>
      </div>
    );
  }

  // View mode — compact
  const details: string[] = [];
  if (property.monthly_rate) details.push(`Rate: $${property.monthly_rate.toFixed(2)}/mo`);
  if (property.gate_code) details.push(`Gate: ${property.gate_code}`);
  if (property.dog_on_property) details.push("Dog on property");
  if (property.access_instructions) details.push(property.access_instructions);

  return (
    <div className="flex items-start gap-2 text-xs text-muted-foreground px-1 py-1">
      <div className="flex-1 min-w-0">
        {showAddress && (
          <div className="flex items-center gap-1.5 mb-0.5">
            <MapPin className="h-3 w-3 shrink-0" />
            <span className="font-medium text-foreground">{property.name || property.address}, {property.city}</span>
          </div>
        )}
        <div className="flex flex-wrap gap-x-3 gap-y-0.5">
          {details.length > 0 ? details.map((item, i) => (
            <span key={i} className={item === "Dog on property" ? "text-amber-600 font-medium" : ""}>{item}</span>
          )) : (
            <span className="italic text-muted-foreground/50">No rate or site details</span>
          )}
        </div>
      </div>
      {perms.canEditCustomers && (
        <Button variant="ghost" size="icon" className="h-6 w-6 shrink-0" onClick={() => setEditing(true)}>
          <Pencil className="h-3 w-3" />
        </Button>
      )}
    </div>
  );
}
