"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  Loader2,
  Package,
  ChevronDown,
  ChevronUp,
  Cog,
  Filter,
  Flame,
  Droplets,
  Cpu,
  ExternalLink,
  Search,
  ShoppingCart,
  AlertCircle,
} from "lucide-react";
import { PartsSearchDialog } from "@/components/parts/parts-search-dialog";
import { LogPurchaseForm } from "@/components/parts/log-purchase-form";
import type { Customer, Property } from "./customer-types";

interface PartItem {
  id: string;
  name: string;
  sku: string;
  brand: string | null;
  category: string | null;
  estimated_price: number | null;
  product_url: string | null;
  image_url: string | null;
}

interface EquipmentGroup {
  water_feature_id: string;
  water_feature_name: string;
  property_id: string;
  equipment_type: string;
  model: string;
  parts: PartItem[];
}

interface CustomerPartsResponse {
  equipment: EquipmentGroup[];
  total_parts: number;
  equipment_without_parts: string[];
}

const EQUIPMENT_ICONS: Record<string, typeof Cog> = {
  pump: Cog,
  filter: Filter,
  heater: Flame,
  chlorinator: Droplets,
  automation: Cpu,
};

const EQUIPMENT_LABELS: Record<string, string> = {
  pump: "Pump",
  filter: "Filter",
  heater: "Heater",
  chlorinator: "Chlorinator",
  automation: "Automation",
};

interface CustomerPartsTabProps {
  customer: Customer;
  properties: Property[];
}

export function CustomerPartsTab({ customer, properties }: CustomerPartsTabProps) {
  const [data, setData] = useState<CustomerPartsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchPropertyId, setSearchPropertyId] = useState<string | undefined>();
  const [searchWfId, setSearchWfId] = useState<string | undefined>();
  const [purchaseTarget, setPurchaseTarget] = useState<{
    propertyId: string;
    waterFeatureId: string;
  } | null>(null);

  useEffect(() => {
    setLoading(true);
    api
      .get<CustomerPartsResponse>(`/v1/parts/customer/${customer.id}`)
      .then((res) => {
        setData(res);
        // Auto-expand groups that have parts
        const autoExpand = new Set<string>();
        for (const eq of res.equipment) {
          if (eq.parts.length > 0) {
            autoExpand.add(`${eq.water_feature_id}:${eq.equipment_type}`);
          }
        }
        setExpanded(autoExpand);
      })
      .catch(() => toast.error("Failed to load parts"))
      .finally(() => setLoading(false));
  }, [customer.id]);

  const toggleExpanded = (key: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const openSearch = (model: string, propertyId: string, wfId: string) => {
    setSearchQuery(model);
    setSearchPropertyId(propertyId);
    setSearchWfId(wfId);
    setSearchOpen(true);
  };

  const openPurchase = (propertyId: string, waterFeatureId: string) => {
    setPurchaseTarget({ propertyId, waterFeatureId });
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!data || data.equipment.length === 0) {
    const hasWfs = properties.some((p) => p.water_features && p.water_features.length > 0);
    return (
      <Card className="shadow-sm">
        <CardContent className="py-12 text-center space-y-3">
          <Package className="h-10 w-10 mx-auto text-muted-foreground" />
          <p className="text-sm text-muted-foreground">
            {hasWfs
              ? "No equipment models recorded on any water features."
              : "No water features found for this customer."}
          </p>
          <p className="text-xs text-muted-foreground">
            Add equipment details on the Water Features tab to see compatible parts.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-3">
      {/* Summary header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Package className="h-4 w-4 text-muted-foreground" />
          <span className="text-sm font-medium">
            {data.total_parts} compatible part{data.total_parts !== 1 ? "s" : ""} found
          </span>
        </div>
        {data.equipment_without_parts.length > 0 && (
          <Badge variant="outline" className="text-xs border-amber-400 text-amber-600">
            {data.equipment_without_parts.length} without parts
          </Badge>
        )}
      </div>

      {/* Equipment groups */}
      {data.equipment.map((eq) => {
        const key = `${eq.water_feature_id}:${eq.equipment_type}`;
        const isOpen = expanded.has(key);
        const Icon = EQUIPMENT_ICONS[eq.equipment_type] || Package;
        const label = EQUIPMENT_LABELS[eq.equipment_type] || eq.equipment_type;
        const hasParts = eq.parts.length > 0;

        return (
          <Card key={key} className="shadow-sm">
            <Collapsible open={isOpen} onOpenChange={() => toggleExpanded(key)}>
              <CollapsibleTrigger asChild>
                <CardHeader className="cursor-pointer py-3 px-4 hover:bg-muted/50 transition-colors">
                  <div className="flex items-center gap-3 w-full">
                    <Icon className="h-4 w-4 text-muted-foreground shrink-0" />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <CardTitle className="text-sm font-medium truncate">
                          {eq.model}
                        </CardTitle>
                        {hasParts ? (
                          <Badge variant="secondary" className="text-[10px] h-4 px-1.5 shrink-0">
                            {eq.parts.length}
                          </Badge>
                        ) : (
                          <Badge variant="outline" className="text-[10px] h-4 px-1.5 border-amber-400 text-amber-600 shrink-0">
                            No parts
                          </Badge>
                        )}
                      </div>
                      <p className="text-xs text-muted-foreground">
                        {label} &middot; {eq.water_feature_name}
                      </p>
                    </div>
                    {isOpen ? (
                      <ChevronUp className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                    ) : (
                      <ChevronDown className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                    )}
                  </div>
                </CardHeader>
              </CollapsibleTrigger>

              <CollapsibleContent>
                <CardContent className="pt-0 pb-3 px-4">
                  {hasParts ? (
                    <div className="space-y-2">
                      {eq.parts.map((part) => (
                        <div
                          key={part.id}
                          className="flex items-start gap-3 rounded-md border p-2.5 bg-muted/30 hover:bg-muted/50 transition-colors"
                        >
                          <div className="flex-shrink-0 h-10 w-10 rounded bg-background border flex items-center justify-center overflow-hidden">
                            {part.image_url ? (
                              <img src={part.image_url} alt="" className="h-full w-full object-cover" />
                            ) : (
                              <Package className="h-4 w-4 text-muted-foreground" />
                            )}
                          </div>
                          <div className="flex-1 min-w-0">
                            <span className="text-sm font-medium leading-tight block truncate">
                              {part.name}
                            </span>
                            <div className="flex items-center gap-2 mt-0.5 flex-wrap">
                              <span className="text-[10px] text-muted-foreground bg-background px-1.5 py-0.5 rounded font-mono border">
                                {part.sku}
                              </span>
                              {part.brand && (
                                <span className="text-xs text-muted-foreground">{part.brand}</span>
                              )}
                              {part.category && (
                                <Badge variant="secondary" className="text-[10px] h-4 px-1.5">
                                  {part.category}
                                </Badge>
                              )}
                              {part.estimated_price !== null && (
                                <span className="text-xs font-medium text-green-600">
                                  ${part.estimated_price.toFixed(2)}
                                </span>
                              )}
                            </div>
                          </div>
                          <div className="flex flex-col gap-1 shrink-0">
                            {part.product_url && (
                              <Button
                                variant="outline"
                                size="sm"
                                className="h-7 text-xs"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  window.open(part.product_url!, "_blank");
                                }}
                              >
                                <ExternalLink className="h-3 w-3 mr-1" />
                                Buy
                              </Button>
                            )}
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-7 text-xs"
                              onClick={(e) => {
                                e.stopPropagation();
                                openPurchase(eq.property_id, eq.water_feature_id);
                              }}
                            >
                              <ShoppingCart className="h-3 w-3 mr-1" />
                              Log
                            </Button>
                          </div>
                        </div>
                      ))}

                      {/* Search for more */}
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-xs text-muted-foreground w-full"
                        onClick={() => openSearch(eq.model, eq.property_id, eq.water_feature_id)}
                      >
                        <Search className="h-3 w-3 mr-1" />
                        Search for more {label.toLowerCase()} parts
                      </Button>
                    </div>
                  ) : (
                    <div className="text-center py-4 space-y-2">
                      <AlertCircle className="h-5 w-5 mx-auto text-amber-500" />
                      <p className="text-xs text-muted-foreground">
                        No parts found in catalog for &ldquo;{eq.model}&rdquo;
                      </p>
                      <Button
                        variant="outline"
                        size="sm"
                        className="text-xs"
                        onClick={() => openSearch(eq.model, eq.property_id, eq.water_feature_id)}
                      >
                        <Search className="h-3 w-3 mr-1" />
                        Search Parts Catalog
                      </Button>
                    </div>
                  )}
                </CardContent>
              </CollapsibleContent>
            </Collapsible>
          </Card>
        );
      })}

      {/* Log purchase form (inline) */}
      {purchaseTarget && (
        <Card className="shadow-sm">
          <CardHeader className="py-3 px-4">
            <CardTitle className="text-sm font-medium">Log Purchase</CardTitle>
          </CardHeader>
          <CardContent className="pt-0 pb-3 px-4">
            <LogPurchaseForm
              propertyId={purchaseTarget.propertyId}
              waterFeatureId={purchaseTarget.waterFeatureId}
              onPurchaseLogged={() => setPurchaseTarget(null)}
              onCancel={() => setPurchaseTarget(null)}
            />
          </CardContent>
        </Card>
      )}

      {/* Search dialog */}
      <PartsSearchDialog
        open={searchOpen}
        onClose={() => setSearchOpen(false)}
        propertyId={searchPropertyId}
        waterFeatureId={searchWfId}
        initialQuery={searchQuery}
      />
    </div>
  );
}
