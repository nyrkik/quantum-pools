"use client";

import { useState, useEffect, useRef } from "react";
import { api, getBackendOrigin } from "@/lib/api";
import { toast } from "sonner";
import { Loader2, Camera, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

interface Vendor {
  id: string;
  name: string;
  provider_type: string;
}

interface LogPurchaseFormProps {
  jobId?: string;
  propertyId?: string;
  waterFeatureId?: string;
  visitChargeId?: string;
  onPurchaseLogged: () => void;
  onCancel?: () => void;
}

function resizeImage(file: File, maxWidth: number): Promise<Blob> {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => {
      let { width, height } = img;
      if (width > maxWidth) {
        height = Math.round((height * maxWidth) / width);
        width = maxWidth;
      }
      const canvas = document.createElement("canvas");
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext("2d")!;
      ctx.drawImage(img, 0, 0, width, height);
      canvas.toBlob((blob) => resolve(blob!), "image/jpeg", 0.85);
    };
    img.src = URL.createObjectURL(file);
  });
}

export function LogPurchaseForm({
  jobId,
  propertyId,
  waterFeatureId,
  visitChargeId,
  onPurchaseLogged,
  onCancel,
}: LogPurchaseFormProps) {
  const [vendors, setVendors] = useState<Vendor[]>([]);
  const [vendorsLoading, setVendorsLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [markup, setMarkup] = useState<number>(25);
  const fileRef = useRef<HTMLInputElement>(null);
  const [receiptFile, setReceiptFile] = useState<File | null>(null);
  const [receiptPreview, setReceiptPreview] = useState<string | null>(null);

  const [form, setForm] = useState({
    description: "",
    sku: "",
    vendor_name: "",
    unit_cost: "",
    quantity: "1",
    notes: "",
  });

  useEffect(() => {
    Promise.all([
      api.get<Vendor[]>("/v1/vendors"),
      api.get<{ default_parts_markup_pct: number }>("/v1/part-purchases/markup"),
    ]).then(([v, m]) => {
      setVendors(v);
      setMarkup(m.default_parts_markup_pct);
      if (v.length > 0) {
        setForm((f) => ({ ...f, vendor_name: v[0].name }));
      }
    }).catch(() => {
      toast.error("Failed to load vendors");
    }).finally(() => setVendorsLoading(false));
  }, []);

  const unitCost = parseFloat(form.unit_cost) || 0;
  const quantity = parseInt(form.quantity) || 1;
  const totalCost = Math.round(unitCost * quantity * 100) / 100;
  const customerPrice = Math.round(totalCost * (1 + markup / 100) * 100) / 100;

  const handleReceiptCapture = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setReceiptFile(file);
    setReceiptPreview(URL.createObjectURL(file));
  };

  const handleSubmit = async () => {
    if (!form.description.trim() || !form.vendor_name.trim() || !unitCost) {
      toast.error("Description, vendor, and unit cost are required");
      return;
    }
    setSaving(true);
    try {
      let receiptUrl: string | undefined;

      // Upload receipt photo if present
      if (receiptFile) {
        const resized = await resizeImage(receiptFile, 1600);
        const fd = new FormData();
        fd.append("file", resized, "receipt.jpg");
        if (propertyId) fd.append("property_id", propertyId);
        const uploadResult = await api.upload<{ url: string }>("/v1/photos/receipt", fd);
        receiptUrl = uploadResult.url;
      }

      await api.post("/v1/part-purchases", {
        description: form.description,
        sku: form.sku || undefined,
        vendor_name: form.vendor_name,
        unit_cost: unitCost,
        quantity,
        markup_pct: markup,
        job_id: jobId || undefined,
        property_id: propertyId || undefined,
        water_feature_id: waterFeatureId || undefined,
        visit_charge_id: visitChargeId || undefined,
        receipt_url: receiptUrl,
        notes: form.notes || undefined,
      });
      toast.success("Purchase logged");
      setForm({ description: "", sku: "", vendor_name: vendors[0]?.name || "", unit_cost: "", quantity: "1", notes: "" });
      setReceiptFile(null);
      setReceiptPreview(null);
      onPurchaseLogged();
    } catch {
      toast.error("Failed to log purchase");
    } finally {
      setSaving(false);
    }
  };

  if (vendorsLoading) {
    return <div className="flex justify-center py-4"><Loader2 className="h-4 w-4 animate-spin text-muted-foreground" /></div>;
  }

  return (
    <div className="space-y-3 border rounded-lg p-4 bg-muted/50">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="sm:col-span-2 space-y-1">
          <Label className="text-xs">Description *</Label>
          <Input
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
            placeholder="Pentair WhisperFlo pump motor"
            className="h-8 text-sm"
          />
        </div>
        <div className="space-y-1">
          <Label className="text-xs">SKU</Label>
          <Input
            value={form.sku}
            onChange={(e) => setForm({ ...form, sku: e.target.value })}
            placeholder="Optional"
            className="h-8 text-sm"
          />
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Vendor *</Label>
          <Select value={form.vendor_name} onValueChange={(v) => setForm({ ...form, vendor_name: v })}>
            <SelectTrigger className="h-8 text-sm">
              <SelectValue placeholder="Select vendor" />
            </SelectTrigger>
            <SelectContent>
              {vendors.map((v) => (
                <SelectItem key={v.id} value={v.name}>{v.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Unit Cost *</Label>
          <div className="relative">
            <span className="absolute left-2.5 top-1.5 text-sm text-muted-foreground">$</span>
            <Input
              type="number"
              step="0.01"
              min="0"
              value={form.unit_cost}
              onChange={(e) => setForm({ ...form, unit_cost: e.target.value })}
              placeholder="0.00"
              className="h-8 text-sm pl-6"
            />
          </div>
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Quantity</Label>
          <Input
            type="number"
            min="1"
            value={form.quantity}
            onChange={(e) => setForm({ ...form, quantity: e.target.value })}
            className="h-8 text-sm"
          />
        </div>
      </div>

      {/* Computed totals */}
      {unitCost > 0 && (
        <div className="flex items-center gap-4 text-xs bg-background rounded-md p-2.5 border">
          <span className="text-muted-foreground">Total: <span className="font-medium text-foreground">${totalCost.toFixed(2)}</span></span>
          <span className="text-muted-foreground">Markup: <span className="font-medium text-foreground">{markup}%</span></span>
          <span className="text-muted-foreground">Customer: <span className="font-medium text-green-600">${customerPrice.toFixed(2)}</span></span>
        </div>
      )}

      {/* Notes */}
      <div className="space-y-1">
        <Label className="text-xs">Notes</Label>
        <Textarea
          value={form.notes}
          onChange={(e) => setForm({ ...form, notes: e.target.value })}
          placeholder="Optional notes..."
          className="text-sm min-h-[2.5rem] resize-none"
          rows={2}
        />
      </div>

      {/* Receipt photo */}
      <div className="space-y-1">
        <Label className="text-xs">Receipt Photo</Label>
        <div className="flex items-center gap-2">
          <input ref={fileRef} type="file" accept="image/*" capture="environment" className="hidden" onChange={handleReceiptCapture} />
          <Button variant="outline" size="sm" className="h-7 text-xs" onClick={() => fileRef.current?.click()}>
            <Camera className="h-3 w-3 mr-1" /> {receiptFile ? "Change" : "Capture"}
          </Button>
          {receiptPreview && (
            <div className="relative">
              <img src={receiptPreview} alt="Receipt" className="h-10 w-10 object-cover rounded border" />
              <button
                onClick={() => { setReceiptFile(null); setReceiptPreview(null); }}
                className="absolute -top-1 -right-1 bg-background border rounded-full p-0.5"
              >
                <X className="h-2.5 w-2.5" />
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Actions */}
      <div className="flex gap-2 pt-1">
        <Button size="sm" onClick={handleSubmit} disabled={saving || !form.description.trim() || !form.vendor_name || !unitCost}>
          {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" /> : null}
          Log Purchase
        </Button>
        {onCancel && (
          <Button variant="ghost" size="sm" onClick={onCancel}>Cancel</Button>
        )}
      </div>
    </div>
  );
}
