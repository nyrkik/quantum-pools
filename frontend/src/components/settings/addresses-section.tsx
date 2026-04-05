"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { toast } from "sonner";
import { Loader2, Check, MapPin } from "lucide-react";

interface Address {
  street: string;
  city: string;
  state: string;
  zip: string;
  same_as?: string;
}

interface Addresses {
  mailing: Address;
  physical: Address;
  billing: Address;
}

const EMPTY_ADDR: Address = { street: "", city: "", state: "", zip: "" };

const LABELS: Record<string, string> = {
  mailing: "Mailing Address",
  physical: "Physical Address",
  billing: "Billing Address",
};

const SAME_AS_LABELS: Record<string, string> = {
  mailing: "Same as mailing",
  physical: "Same as physical",
  billing: "Same as billing",
};

export function AddressesSection() {
  const [addresses, setAddresses] = useState<Addresses>({
    mailing: { ...EMPTY_ADDR },
    physical: { same_as: "mailing", ...EMPTY_ADDR },
    billing: { same_as: "mailing", ...EMPTY_ADDR },
  });
  const [original, setOriginal] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await api.get<{ addresses: Addresses }>("/v1/branding/addresses");
      const a = data.addresses || {};
      const full: Addresses = {
        mailing: a.mailing || { ...EMPTY_ADDR },
        physical: a.physical || { same_as: "mailing", ...EMPTY_ADDR },
        billing: a.billing || { same_as: "mailing", ...EMPTY_ADDR },
      };
      setAddresses(full);
      setOriginal(JSON.stringify(full));
    } catch {} finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const isDirty = useMemo(() => JSON.stringify(addresses) !== original, [addresses, original]);

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.put("/v1/branding/addresses", { addresses });
      setOriginal(JSON.stringify(addresses));
      toast.success("Addresses saved");
    } catch {
      toast.error("Failed to save addresses");
    } finally { setSaving(false); }
  };

  const updateField = (type: keyof Addresses, field: string, value: string) => {
    setAddresses((prev) => ({
      ...prev,
      [type]: { ...prev[type], [field]: value, same_as: undefined },
    }));
  };

  const toggleSameAs = (type: "physical" | "billing", sameAs: string, checked: boolean) => {
    if (checked) {
      setAddresses((prev) => ({
        ...prev,
        [type]: { ...EMPTY_ADDR, same_as: sameAs },
      }));
    } else {
      // Copy the source address so fields are pre-filled
      const source = addresses[sameAs as keyof Addresses];
      const copied = source.same_as ? { ...EMPTY_ADDR } : { ...source, same_as: undefined };
      setAddresses((prev) => ({ ...prev, [type]: copied }));
    }
  };

  if (loading) {
    return (
      <Card className="shadow-sm">
        <CardContent className="flex justify-center py-8">
          <Loader2 className="h-5 w-5 animate-spin" />
        </CardContent>
      </Card>
    );
  }

  const renderAddressFields = (type: keyof Addresses) => {
    const addr = addresses[type];
    const isSameAs = !!addr.same_as;

    return (
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <Label className="text-sm font-medium">{LABELS[type]}</Label>
        </div>

        {/* Same-as checkboxes for physical and billing */}
        {type !== "mailing" && (
          <div className="flex gap-4">
            {(["mailing", "physical", "billing"] as const)
              .filter((k) => k !== type)
              .map((source) => (
                <label key={source} className="flex items-center gap-1.5 text-xs">
                  <Checkbox
                    checked={addr.same_as === source}
                    onCheckedChange={(checked) => toggleSameAs(type as "physical" | "billing", source, !!checked)}
                  />
                  {SAME_AS_LABELS[source]}
                </label>
              ))}
          </div>
        )}

        {!isSameAs && (
          <div className="space-y-2">
            <Input
              placeholder="Street address"
              value={addr.street || ""}
              onChange={(e) => updateField(type, "street", e.target.value)}
              className="h-8 text-sm"
            />
            <div className="grid grid-cols-3 gap-2">
              <Input
                placeholder="City"
                value={addr.city || ""}
                onChange={(e) => updateField(type, "city", e.target.value)}
                className="h-8 text-sm"
              />
              <Input
                placeholder="State"
                value={addr.state || ""}
                onChange={(e) => updateField(type, "state", e.target.value)}
                className="h-8 text-sm"
              />
              <Input
                placeholder="ZIP"
                value={addr.zip || ""}
                onChange={(e) => updateField(type, "zip", e.target.value)}
                className="h-8 text-sm"
              />
            </div>
          </div>
        )}

        {isSameAs && (
          <p className="text-xs text-muted-foreground italic">
            Using {LABELS[addr.same_as!]?.toLowerCase()}
          </p>
        )}
      </div>
    );
  };

  return (
    <Card className="shadow-sm">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base flex items-center gap-1.5">
            <MapPin className="h-4 w-4 text-muted-foreground" />
            Addresses
          </CardTitle>
          {isDirty && (
            <Button size="sm" onClick={handleSave} disabled={saving}>
              {saving ? <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" /> : <Check className="h-3.5 w-3.5 mr-1" />}
              Save
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {renderAddressFields("mailing")}
        <div className="border-t" />
        {renderAddressFields("physical")}
        <div className="border-t" />
        {renderAddressFields("billing")}
      </CardContent>
    </Card>
  );
}
