"use client";

import { useState, useEffect, useRef } from "react";
import { api } from "@/lib/api";
import { resizeImage } from "@/lib/image-utils";
import { toast } from "sonner";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
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
import { Plus, Camera, Loader2, X, Receipt } from "lucide-react";

interface ChargeTemplate {
  id: string;
  name: string;
  default_amount: number;
  category: string;
  is_taxable: boolean;
  requires_approval: boolean;
}

interface AddChargeSheetProps {
  propertyId: string;
  customerId: string;
  visitId?: string;
  onChargeAdded?: () => void;
  trigger?: React.ReactNode;
}

const CATEGORIES = [
  { value: "time", label: "Time" },
  { value: "chemical", label: "Chemical" },
  { value: "material", label: "Material" },
  { value: "other", label: "Other" },
];

export function AddChargeSheet({
  propertyId,
  customerId,
  visitId,
  onChargeAdded,
  trigger,
}: AddChargeSheetProps) {
  const [open, setOpen] = useState(false);
  const [templates, setTemplates] = useState<ChargeTemplate[]>([]);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [step, setStep] = useState<"pick" | "form">("pick");
  const fileRef = useRef<HTMLInputElement>(null);

  // Form state
  const [selectedTemplate, setSelectedTemplate] = useState<ChargeTemplate | null>(null);
  const [description, setDescription] = useState("");
  const [amount, setAmount] = useState("");
  const [category, setCategory] = useState("other");
  const [notes, setNotes] = useState("");
  const [photoFile, setPhotoFile] = useState<File | null>(null);
  const [photoPreview, setPhotoPreview] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setLoading(true);
      api
        .get<ChargeTemplate[]>("/v1/charge-templates")
        .then(setTemplates)
        .catch(() => toast.error("Failed to load charge templates"))
        .finally(() => setLoading(false));
    }
  }, [open]);

  const reset = () => {
    setStep("pick");
    setSelectedTemplate(null);
    setDescription("");
    setAmount("");
    setCategory("other");
    setNotes("");
    setPhotoFile(null);
    setPhotoPreview(null);
  };

  const selectTemplate = (tmpl: ChargeTemplate | null) => {
    setSelectedTemplate(tmpl);
    if (tmpl) {
      setDescription(tmpl.name);
      setAmount(tmpl.default_amount.toFixed(2));
      setCategory(tmpl.category);
    } else {
      setDescription("");
      setAmount("");
      setCategory("other");
    }
    setStep("form");
  };

  const handlePhoto = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setPhotoFile(file);
    setPhotoPreview(URL.createObjectURL(file));
  };

  const removePhoto = () => {
    setPhotoFile(null);
    setPhotoPreview(null);
    if (fileRef.current) fileRef.current.value = "";
  };

  const handleSubmit = async () => {
    if (!description.trim() || !amount) {
      toast.error("Description and amount are required");
      return;
    }

    setSubmitting(true);
    try {
      const charge = await api.post<{
        id: string;
        status: string;
        amount: number;
      }>("/v1/visit-charges", {
        property_id: propertyId,
        customer_id: customerId,
        visit_id: visitId || null,
        template_id: selectedTemplate?.id || null,
        description: description.trim(),
        amount: parseFloat(amount),
        category,
        notes: notes.trim() || null,
      });

      // Upload photo if provided
      if (photoFile && charge.id) {
        setUploading(true);
        try {
          const resized = await resizeImage(photoFile, 1600);
          const formData = new FormData();
          formData.append("photo", resized, photoFile.name);
          await api.upload(`/v1/visit-charges/${charge.id}/photo`, formData);
        } catch {
          toast.error("Charge saved but photo upload failed");
        }
        setUploading(false);
      }

      if (charge.status === "approved") {
        toast.success("Charge added");
      } else {
        toast.success(
          `Submitted for approval — above $${parseFloat(amount).toFixed(0)} threshold`
        );
      }

      reset();
      setOpen(false);
      onChargeAdded?.();
    } catch (err: unknown) {
      const msg =
        err && typeof err === "object" && "message" in err
          ? (err as { message: string }).message
          : "Failed to create charge";
      toast.error(msg);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Sheet open={open} onOpenChange={(v) => { setOpen(v); if (!v) reset(); }}>
      <SheetTrigger asChild>
        {trigger || (
          <Button size="sm" variant="outline">
            <Receipt className="h-3.5 w-3.5 mr-1.5" />
            Add Charge
          </Button>
        )}
      </SheetTrigger>
      <SheetContent side="bottom" className="max-h-[85vh] overflow-y-auto sm:max-w-lg sm:mx-auto sm:rounded-t-xl">
        <SheetHeader className="pb-4">
          <SheetTitle className="text-base">
            {step === "pick" ? "Select Charge Type" : "Add Charge"}
          </SheetTitle>
        </SheetHeader>

        {loading ? (
          <div className="flex justify-center py-8">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : step === "pick" ? (
          <div className="space-y-3 pb-4">
            <div className="grid grid-cols-2 gap-2">
              {templates.map((tmpl) => (
                <button
                  key={tmpl.id}
                  onClick={() => selectTemplate(tmpl)}
                  className="flex flex-col items-start gap-1 rounded-lg border p-3 text-left transition-colors hover:bg-accent/50 active:bg-accent"
                >
                  <span className="text-sm font-medium leading-tight">
                    {tmpl.name}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    ${tmpl.default_amount.toFixed(0)}
                    {tmpl.requires_approval && " · Approval required"}
                  </span>
                </button>
              ))}
              <button
                onClick={() => selectTemplate(null)}
                className="flex flex-col items-center justify-center gap-1 rounded-lg border border-dashed p-3 text-center transition-colors hover:bg-accent/50 active:bg-accent"
              >
                <Plus className="h-4 w-4 text-muted-foreground" />
                <span className="text-sm font-medium">Custom</span>
              </button>
            </div>
          </div>
        ) : (
          <div className="space-y-4 pb-4">
            {/* Back button */}
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setStep("pick")}
              className="text-muted-foreground -ml-2"
            >
              Back
            </Button>

            <div className="space-y-1.5">
              <Label className="text-sm">Description</Label>
              <Input
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Describe the charge"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label className="text-sm">Amount</Label>
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">
                    $
                  </span>
                  <Input
                    type="number"
                    step="0.01"
                    min="0"
                    value={amount}
                    onChange={(e) => setAmount(e.target.value)}
                    className="pl-7"
                    inputMode="decimal"
                  />
                </div>
              </div>
              <div className="space-y-1.5">
                <Label className="text-sm">Category</Label>
                <Select value={category} onValueChange={setCategory}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {CATEGORIES.map((c) => (
                      <SelectItem key={c.value} value={c.value}>
                        {c.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            {/* Photo */}
            <div className="space-y-1.5">
              <Label className="text-sm">Photo (optional)</Label>
              {photoPreview ? (
                <div className="relative inline-block">
                  <img
                    src={photoPreview}
                    alt="Evidence"
                    className="h-24 w-auto rounded-lg border object-cover"
                  />
                  <button
                    onClick={removePhoto}
                    className="absolute -top-2 -right-2 rounded-full bg-destructive p-0.5 text-destructive-foreground shadow"
                  >
                    <X className="h-3 w-3" />
                  </button>
                </div>
              ) : (
                <>
                  <input
                    ref={fileRef}
                    type="file"
                    accept="image/jpeg,image/png,image/webp"
                    capture="environment"
                    className="hidden"
                    onChange={handlePhoto}
                  />
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => fileRef.current?.click()}
                  >
                    <Camera className="h-3.5 w-3.5 mr-1.5" />
                    Take Photo
                  </Button>
                </>
              )}
            </div>

            <div className="space-y-1.5">
              <Label className="text-sm">Notes (optional)</Label>
              <Textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Additional details..."
                rows={2}
              />
            </div>

            <Button
              onClick={handleSubmit}
              disabled={submitting || uploading || !description.trim() || !amount}
              className="w-full"
            >
              {submitting || uploading ? (
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
              ) : (
                <Receipt className="h-4 w-4 mr-2" />
              )}
              {uploading ? "Uploading photo..." : "Submit Charge"}
            </Button>
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
