"use client";

import { useRef } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ArrowLeft, X, Loader2, AlertTriangle } from "lucide-react";
import type { Permissions } from "@/lib/permissions";
import type { Customer, Property, WaterFeature, RateSplitData, PropertyPhoto } from "./customer-types";
import type { ViewTab } from "./customer-sidebar";
import { WfTile, type WaterFeature as WfTileWF, type TechAssignment } from "@/components/water-features/wf-tile";
import { AddWfForm } from "@/components/water-features/add-wf-form";
import { AddPropertyForm } from "@/components/properties/add-property-form";
import { PropertySiteDetails } from "@/components/properties/property-site-details";
import { getBackendOrigin } from "@/lib/api";

const API_BASE = typeof window !== "undefined" ? getBackendOrigin() : "http://localhost:7061";

interface CustomerWfsTabProps {
  customer: Customer;
  customerId: string;
  properties: Property[];
  fullWfs: WaterFeature[];
  heroImages: Record<string, PropertyPhoto>;
  techAssignments: Record<string, Array<{ tech_id: string; tech_name: string; color: string; service_days: string[] }>>;
  wfProfitability: Record<string, { margin_pct: number; suggested_rate: number }>;
  perms: Permissions;
  activeProperty: Property | null;
  selectedWfId: string | null;
  scrollToPropId: string | null;
  wfsNeedRateSplit: boolean;
  // Rate split
  showRateSplit: boolean;
  rateSplitData: RateSplitData | null;
  rateSplitEdits: Record<string, number>;
  rateSplitSaving: boolean;
  // Callbacks
  onTabChange: (tab: ViewTab) => void;
  onWfSelect: (id: string | null) => void;
  onScrollToPropClear: () => void;
  onOpenRateSplit: () => void;
  onCloseRateSplit: () => void;
  onApplyRateSplit: () => void;
  onRateSplitEditChange: (wfId: string, value: number) => void;
  onLoad: () => void;
}

export function CustomerWfsTab({
  customer,
  customerId,
  properties,
  fullWfs,
  heroImages,
  techAssignments,
  wfProfitability,
  perms,
  activeProperty,
  selectedWfId,
  scrollToPropId,
  wfsNeedRateSplit,
  showRateSplit,
  rateSplitData,
  rateSplitEdits,
  rateSplitSaving,
  onTabChange,
  onWfSelect,
  onScrollToPropClear,
  onOpenRateSplit,
  onCloseRateSplit,
  onApplyRateSplit,
  onRateSplitEditChange,
  onLoad,
}: CustomerWfsTabProps) {
  const wfRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const propRefs = useRef<Record<string, HTMLDivElement | null>>({});

  // Scroll to selected WF or property on mount
  // Note: The parent page handles the effect trigger via scrollToPropId/selectedWfId
  // We just need the refs for scrolling
  if (typeof window !== "undefined") {
    if (selectedWfId && wfRefs.current[selectedWfId]) {
      setTimeout(() => {
        wfRefs.current[selectedWfId]?.scrollIntoView({ behavior: "smooth", block: "start" });
      }, 100);
    }
    if (scrollToPropId && propRefs.current[scrollToPropId]) {
      setTimeout(() => {
        propRefs.current[scrollToPropId]?.scrollIntoView({ behavior: "smooth", block: "start" });
        onScrollToPropClear();
      }, 100);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="sm" className="shrink-0" onClick={() => { onWfSelect(null); onTabChange("overview"); }}>
          <ArrowLeft className="h-4 w-4 mr-1" />
          Back to Overview
        </Button>
        {perms.canEditCustomers && (
          <AddPropertyForm customerId={customerId} onCreated={onLoad} />
        )}
      </div>
      {wfsNeedRateSplit && (
        <div className="flex items-center justify-between gap-3 px-4 py-3 bg-amber-50 dark:bg-amber-950/20 border border-amber-200/50 dark:border-amber-800/50 rounded-lg">
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-amber-500 shrink-0" />
            <span className="text-sm">
              <span className="font-medium">Rate not split across water features.</span>
              <span className="text-muted-foreground ml-1">Account rate is ${customer?.monthly_rate?.toFixed(0)}/mo but individual water features have no rates assigned.</span>
            </span>
          </div>
          <Button size="sm" className="shrink-0" onClick={onOpenRateSplit}>Split Rates</Button>
        </div>
      )}

      {/* Rate Split Dialog */}
      {showRateSplit && rateSplitData && (
        <Card className="shadow-sm border-primary/30">
          <CardContent className="p-4">
            <div className="flex items-center justify-between mb-3">
              <div>
                <h3 className="text-sm font-semibold">Split Rate Across Water Features</h3>
                <p className="text-xs text-muted-foreground">
                  Total: ${rateSplitData.total_rate.toFixed(2)}/mo · Method: {rateSplitData.method || "type weight"}
                </p>
              </div>
              <Button variant="ghost" size="icon" onClick={onCloseRateSplit}>
                <X className="h-4 w-4" />
              </Button>
            </div>
            <div className="space-y-2">
              {rateSplitData.allocations.map((a) => (
                <div key={a.wf_id} className="flex items-center gap-3 bg-muted/50 rounded-md px-3 py-2">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium">{a.wf_name || a.water_type}</p>
                    <p className="text-xs text-muted-foreground capitalize">{a.water_type}{a.gallons ? ` · ${a.gallons.toLocaleString()} gal` : ""}</p>
                  </div>
                  {a.current_rate != null && (
                    <span className="text-xs text-muted-foreground">was ${a.current_rate.toFixed(0)}</span>
                  )}
                  <div className="flex items-center gap-1">
                    <span className="text-sm text-muted-foreground">$</span>
                    <Input
                      type="number"
                      value={rateSplitEdits[a.wf_id] ?? a.proposed_rate}
                      onChange={(e) => onRateSplitEditChange(a.wf_id, parseFloat(e.target.value) || 0)}
                      className="w-24 h-8 text-sm text-right"
                    />
                    <span className="text-xs text-muted-foreground">/mo</span>
                  </div>
                </div>
              ))}
            </div>
            <div className="flex items-center justify-between mt-3 pt-3 border-t">
              <p className="text-xs text-muted-foreground">
                Total: ${Object.values(rateSplitEdits).reduce((s, v) => s + v, 0).toFixed(2)}/mo
                {Math.abs(Object.values(rateSplitEdits).reduce((s, v) => s + v, 0) - rateSplitData.total_rate) > 0.01 && (
                  <span className="text-amber-600 ml-2">
                    ({Object.values(rateSplitEdits).reduce((s, v) => s + v, 0) > rateSplitData.total_rate ? "+" : ""}
                    {(Object.values(rateSplitEdits).reduce((s, v) => s + v, 0) - rateSplitData.total_rate).toFixed(2)} from account rate)
                  </span>
                )}
              </p>
              <div className="flex gap-2">
                <Button variant="ghost" size="sm" onClick={onCloseRateSplit}>Cancel</Button>
                <Button size="sm" onClick={onApplyRateSplit} disabled={rateSplitSaving}>
                  {rateSplitSaving ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : null}
                  Apply Rates
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {properties.length === 0 && (
        <Card className="shadow-sm">
          <CardContent className="py-6">
            <p className="text-center text-muted-foreground text-sm">No service location yet</p>
          </CardContent>
        </Card>
      )}
      {(activeProperty ? [activeProperty] : properties).map((prop) => {
        const propWfs = fullWfs.filter((b) => b.property_id === prop.id);
        const summaryWfs = prop.water_features || [];
        const wfs = propWfs.length > 0 ? propWfs : summaryWfs;
        const hero = heroImages[prop.id];
        const hasBows = wfs.length > 0;
        const firstTech = techAssignments[prop.id]?.[0];

        return (
          <div key={prop.id} ref={(el) => { propRefs.current[prop.id] = el; }} className="space-y-4">
            {/* Property header with satellite */}
            {hero && (
              <div className="relative rounded-lg overflow-hidden border">
                <img
                  src={`${API_BASE}${hero.url}`}
                  alt="Property photo"
                  className="w-full h-40 object-cover"
                />
              </div>
            )}

            {/* Property site details — address, gate, dog, access */}
            <PropertySiteDetails
              property={prop}
              perms={perms}
              showAddress={properties.length > 1}
              onUpdated={onLoad}
            />

            {/* WF Tiles */}
            {hasBows ? (
              wfs.map((wf) => {
                const isFull = "pump_type" in wf;
                const fullBow = isFull ? (wf as WaterFeature) : null;
                if (fullBow) {
                  return (
                    <div
                      key={wf.id}
                      ref={(el) => { wfRefs.current[wf.id] = el; }}
                      className={`rounded-lg transition-all duration-500 ${selectedWfId === wf.id ? "ring-2 ring-primary ring-offset-2" : ""}`}
                    >
                      <WfTile
                        wf={fullBow as WfTileWF}
                        propertyId={prop.id}
                        perms={perms}
                        techAssignment={firstTech as TechAssignment | undefined}
                        marginPct={wfProfitability[wf.id]?.margin_pct ?? null}
                        suggestedRate={wfProfitability[wf.id]?.suggested_rate ?? null}
                        customerType={customer?.customer_type}
                        collapsed={selectedWfId !== null && selectedWfId !== wf.id}
                        onExpand={() => onWfSelect(wf.id)}
                        onUpdated={onLoad}
                        onDeleted={onLoad}
                      />
                    </div>
                  );
                }
                return null;
              })
            ) : (
              <p className="text-center text-muted-foreground py-4 text-sm">No water features yet</p>
            )}

            {/* Add Water Feature button per property */}
            {perms.canEditCustomers && (
              <AddWfForm propertyId={prop.id} customerType={customer?.customer_type} onCreated={onLoad} />
            )}
          </div>
        );
      })}

      {/* Visit history placeholder */}
      <Card className="shadow-sm">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">Visit History</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center py-8 text-sm text-muted-foreground">
            Visit history will appear after 3+ service visits
          </div>
        </CardContent>
      </Card>

      {/* Chemical trends placeholder */}
      <Card className="shadow-sm">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">Chemical Trends</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center py-8 text-sm text-muted-foreground">
            Chemical trends will appear after readings are recorded
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
