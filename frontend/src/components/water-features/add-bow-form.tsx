"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";
import { Plus, Loader2 } from "lucide-react";

interface AddBowFormProps {
  propertyId: string;
  onCreated: () => void;
}

export function AddBowForm({ propertyId, onCreated }: AddBowFormProps) {
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [name, setName] = useState("");
  const [waterType, setWaterType] = useState("pool");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      await api.post(`/v1/bodies-of-water/property/${propertyId}`, {
        name: name || undefined,
        water_type: waterType,
        estimated_service_minutes: 30,
      });
      toast.success("Water feature added");
      setName("");
      setWaterType("pool");
      setOpen(false);
      onCreated();
    } catch {
      toast.error("Failed to add water feature");
    } finally {
      setSaving(false);
    }
  };

  if (!open) {
    return (
      <Button variant="outline" size="sm" className="h-8" onClick={() => setOpen(true)}>
        <Plus className="h-3.5 w-3.5 mr-1" />
        Add Water Feature
      </Button>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="border rounded-lg p-4 space-y-3 bg-muted/30">
      <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">New Water Feature</p>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label className="text-xs">Type</Label>
          <Select value={waterType} onValueChange={setWaterType}>
            <SelectTrigger className="h-8 text-sm"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="pool">Pool</SelectItem>
              <SelectItem value="spa">Spa</SelectItem>
              <SelectItem value="hot_tub">Hot Tub</SelectItem>
              <SelectItem value="wading_pool">Wading Pool</SelectItem>
              <SelectItem value="fountain">Fountain</SelectItem>
              <SelectItem value="water_feature">Water Feature</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">Name <span className="text-muted-foreground">(optional)</span></Label>
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Lap Pool" className="h-8 text-sm" />
        </div>
      </div>
      <div className="flex gap-2">
        <Button type="button" variant="outline" size="sm" className="flex-1 h-8" onClick={() => { setOpen(false); setName(""); setWaterType("pool"); }}>
          Cancel
        </Button>
        <Button type="submit" size="sm" className="flex-1 h-8" disabled={saving}>
          {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Add"}
        </Button>
      </div>
    </form>
  );
}
