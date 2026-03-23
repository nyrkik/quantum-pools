"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import { Plus, Loader2 } from "lucide-react";

interface AddPropertyFormProps {
  customerId: string;
  onCreated: () => void;
}

export function AddPropertyForm({ customerId, onCreated }: AddPropertyFormProps) {
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [name, setName] = useState("");
  const [address, setAddress] = useState("");
  const [city, setCity] = useState("");
  const [state, setState] = useState("CA");
  const [zip, setZip] = useState("");

  const reset = () => { setName(""); setAddress(""); setCity(""); setState("CA"); setZip(""); };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!address.trim() || !city.trim() || !zip.trim()) {
      toast.error("Address, city, and zip are required");
      return;
    }
    setSaving(true);
    try {
      await api.post("/v1/properties", {
        customer_id: customerId,
        name: name || undefined,
        address: address.trim(),
        city: city.trim(),
        state: state.trim(),
        zip_code: zip.trim(),
      });
      toast.success("Property added");
      reset();
      setOpen(false);
      onCreated();
    } catch {
      toast.error("Failed to add property");
    } finally {
      setSaving(false);
    }
  };

  if (!open) {
    return (
      <Button variant="outline" size="sm" className="h-8" onClick={() => setOpen(true)}>
        <Plus className="h-3.5 w-3.5 mr-1" />
        Add Property
      </Button>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="border rounded-lg p-4 space-y-3 bg-muted/30">
      <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">New Property</p>
      <div className="space-y-1.5">
        <Label className="text-xs">Name <span className="text-muted-foreground">(optional)</span></Label>
        <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. East Campus" className="h-8 text-sm" />
      </div>
      <div className="space-y-1.5">
        <Label className="text-xs">Address</Label>
        <Input value={address} onChange={(e) => setAddress(e.target.value)} placeholder="123 Main St" className="h-8 text-sm" required />
      </div>
      <div className="grid grid-cols-3 gap-3">
        <div className="space-y-1.5">
          <Label className="text-xs">City</Label>
          <Input value={city} onChange={(e) => setCity(e.target.value)} className="h-8 text-sm" required />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">State</Label>
          <Input value={state} onChange={(e) => setState(e.target.value)} className="h-8 text-sm" required />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">Zip</Label>
          <Input value={zip} onChange={(e) => setZip(e.target.value)} className="h-8 text-sm" required />
        </div>
      </div>
      <div className="flex gap-2">
        <Button type="button" variant="outline" size="sm" className="flex-1 h-8" onClick={() => { setOpen(false); reset(); }}>
          Cancel
        </Button>
        <Button type="submit" size="sm" className="flex-1 h-8" disabled={saving}>
          {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Add"}
        </Button>
      </div>
    </form>
  );
}
