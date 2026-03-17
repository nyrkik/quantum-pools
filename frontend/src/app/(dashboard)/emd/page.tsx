"use client";

import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Shield,
  Search,
  Building2,
  AlertTriangle,
  ClipboardCheck,
  Link2,
  ChevronDown,
  ChevronUp,
  Loader2,
  Wrench,
  ArrowLeft,
  X,
} from "lucide-react";

interface EMDFacilityListItem {
  id: string;
  name: string;
  street_address: string | null;
  city: string | null;
  facility_id: string | null;
  facility_type: string | null;
  matched_property_id: string | null;
  total_inspections: number;
  total_violations: number;
  last_inspection_date: string | null;
}

interface EMDInspection {
  id: string;
  facility_id: string;
  inspection_id: string | null;
  inspection_date: string | null;
  inspection_type: string | null;
  inspector_name: string | null;
  total_violations: number;
  major_violations: number;
  pool_capacity_gallons: number | null;
  flow_rate_gpm: number | null;
  pdf_path: string | null;
  report_notes: string | null;
  closure_status: string | null;
  created_at: string;
  violations?: EMDViolation[];
}

interface EMDViolation {
  id: string;
  violation_code: string | null;
  violation_title: string | null;
  observations: string | null;
  is_major_violation: boolean;
  severity_level: string | null;
  shorthand_summary: string | null;
}

interface EMDEquipment {
  id: string;
  pool_capacity_gallons: number | null;
  flow_rate_gpm: number | null;
  filter_pump_1_make: string | null;
  filter_pump_1_model: string | null;
  filter_pump_1_hp: string | null;
  filter_1_type: string | null;
  filter_1_make: string | null;
  filter_1_model: string | null;
  sanitizer_1_type: string | null;
  sanitizer_1_details: string | null;
  main_drain_type: string | null;
  main_drain_model: string | null;
  main_drain_install_date: string | null;
  equalizer_model: string | null;
  equalizer_install_date: string | null;
}

interface EMDFacilityDetail {
  id: string;
  name: string;
  street_address: string | null;
  city: string | null;
  state: string;
  zip_code: string | null;
  phone: string | null;
  facility_id: string | null;
  permit_holder: string | null;
  facility_type: string | null;
  matched_property_id: string | null;
  matched_at: string | null;
  inspections: EMDInspection[];
  total_inspections: number;
  total_violations: number;
  last_inspection_date: string | null;
  matched_property_address: string | null;
  matched_customer_name: string | null;
}

export default function EMDPage() {
  const [facilities, setFacilities] = useState<EMDFacilityListItem[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [selectedFacility, setSelectedFacility] = useState<EMDFacilityDetail | null>(null);
  const [selectedEquipment, setSelectedEquipment] = useState<EMDEquipment | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [expandedInspection, setExpandedInspection] = useState<string | null>(null);

  const fetchFacilities = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (search) params.set("search", search);
      params.set("limit", "100");
      const data = await api.get<EMDFacilityListItem[]>(
        `/v1/emd/facilities?${params.toString()}`
      );
      setFacilities(data);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [search]);

  useEffect(() => {
    const timer = setTimeout(fetchFacilities, 300);
    return () => clearTimeout(timer);
  }, [fetchFacilities]);

  const selectFacility = async (id: string) => {
    setDetailLoading(true);
    setSelectedEquipment(null);
    try {
      const [detail, equipment] = await Promise.all([
        api.get<EMDFacilityDetail>(`/v1/emd/facilities/${id}`),
        api.get<EMDEquipment | null>(`/v1/emd/facilities/${id}/equipment`),
      ]);
      setSelectedFacility(detail);
      setSelectedEquipment(equipment);
      setExpandedInspection(null);
    } catch {
      // ignore
    } finally {
      setDetailLoading(false);
    }
  };

  const formatDate = (d: string | null) => {
    if (!d) return "--";
    return new Date(d + "T00:00:00").toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  };

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">EMD Intelligence</h1>
        <p className="text-muted-foreground">
          Sacramento County inspection data — {facilities.length} facilities
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
        {/* Left: Facility list */}
        <div className={selectedFacility ? "lg:col-span-2" : "lg:col-span-5"}>
          <Card className="shadow-sm">
            <CardHeader className="pb-3">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Search facilities..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className="pl-9"
                />
              </div>
            </CardHeader>
            <CardContent className="p-0">
              {loading ? (
                <div className="flex items-center justify-center py-12">
                  <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                </div>
              ) : (
                <div className="max-h-[calc(100vh-240px)] overflow-y-auto">
                  <Table>
                    <TableHeader>
                      <TableRow className="bg-slate-100 dark:bg-slate-800">
                        <TableHead className="text-xs font-medium uppercase tracking-wide">
                          Facility
                        </TableHead>
                        <TableHead className="text-xs font-medium uppercase tracking-wide text-center w-20">
                          Insp
                        </TableHead>
                        <TableHead className="text-xs font-medium uppercase tracking-wide text-center w-20">
                          Viol
                        </TableHead>
                        <TableHead className="text-xs font-medium uppercase tracking-wide w-28">
                          Last
                        </TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {facilities.map((f, i) => (
                        <TableRow
                          key={f.id}
                          className={`cursor-pointer ${
                            selectedFacility?.id === f.id
                              ? "bg-blue-50 dark:bg-blue-950"
                              : i % 2 === 1
                              ? "bg-slate-50 dark:bg-slate-900"
                              : ""
                          } hover:bg-blue-50 dark:hover:bg-blue-950`}
                          onClick={() => selectFacility(f.id)}
                        >
                          <TableCell className="py-2">
                            <div className="flex items-center gap-2">
                              {f.matched_property_id && (
                                <Link2 className="h-3 w-3 text-green-500 flex-shrink-0" />
                              )}
                              <div className="min-w-0">
                                <p className="text-sm font-medium truncate">{f.name}</p>
                                <p className="text-xs text-muted-foreground truncate">
                                  {f.street_address}{f.city ? `, ${f.city}` : ""}
                                </p>
                              </div>
                            </div>
                          </TableCell>
                          <TableCell className="text-center text-sm">{f.total_inspections}</TableCell>
                          <TableCell className="text-center">
                            <Badge
                              variant={f.total_violations > 10 ? "destructive" : f.total_violations > 0 ? "secondary" : "outline"}
                              className="text-xs"
                            >
                              {f.total_violations}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-xs text-muted-foreground">
                            {formatDate(f.last_inspection_date)}
                          </TableCell>
                        </TableRow>
                      ))}
                      {facilities.length === 0 && (
                        <TableRow>
                          <TableCell colSpan={4} className="text-center py-8 text-muted-foreground">
                            No facilities found
                          </TableCell>
                        </TableRow>
                      )}
                    </TableBody>
                  </Table>
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Right: Detail panel */}
        {selectedFacility && (
          <div className="lg:col-span-3 space-y-4">
            {detailLoading ? (
              <Card className="shadow-sm">
                <CardContent className="flex items-center justify-center py-12">
                  <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                </CardContent>
              </Card>
            ) : (
              <>
                {/* Facility Info */}
                <Card className="shadow-sm">
                  <CardHeader className="pb-3">
                    <div className="flex items-start justify-between">
                      <div>
                        <CardTitle className="flex items-center gap-2 text-lg">
                          <Building2 className="h-4 w-4" />
                          {selectedFacility.name}
                        </CardTitle>
                        <p className="text-sm text-muted-foreground mt-1">
                          {selectedFacility.street_address}
                          {selectedFacility.city ? `, ${selectedFacility.city}` : ""}
                          {selectedFacility.state ? `, ${selectedFacility.state}` : ""}
                          {selectedFacility.zip_code ? ` ${selectedFacility.zip_code}` : ""}
                        </p>
                      </div>
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => setSelectedFacility(null)}
                      >
                        <X className="h-4 w-4 text-muted-foreground hover:text-destructive" />
                      </Button>
                    </div>
                  </CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
                      {selectedFacility.facility_id && (
                        <div>
                          <span className="text-muted-foreground">Permit ID</span>
                          <p className="font-medium">{selectedFacility.facility_id}</p>
                        </div>
                      )}
                      {selectedFacility.facility_type && (
                        <div>
                          <span className="text-muted-foreground">Type</span>
                          <p className="font-medium">{selectedFacility.facility_type}</p>
                        </div>
                      )}
                      {selectedFacility.permit_holder && (
                        <div>
                          <span className="text-muted-foreground">Permit Holder</span>
                          <p className="font-medium">{selectedFacility.permit_holder}</p>
                        </div>
                      )}
                      {selectedFacility.phone && (
                        <div>
                          <span className="text-muted-foreground">Phone</span>
                          <p className="font-medium">{selectedFacility.phone}</p>
                        </div>
                      )}
                    </div>

                    {/* Match status */}
                    <div className="mt-4 pt-3 border-t">
                      {selectedFacility.matched_property_id ? (
                        <div className="flex items-center gap-2">
                          <Link2 className="h-4 w-4 text-green-500" />
                          <span className="text-sm">
                            Matched to{" "}
                            <span className="font-medium">
                              {selectedFacility.matched_customer_name}
                            </span>
                            {selectedFacility.matched_property_address && (
                              <span className="text-muted-foreground">
                                {" "}— {selectedFacility.matched_property_address}
                              </span>
                            )}
                          </span>
                        </div>
                      ) : (
                        <div className="flex items-center gap-2 text-muted-foreground">
                          <Link2 className="h-4 w-4" />
                          <span className="text-sm">Not matched to any customer</span>
                        </div>
                      )}
                    </div>

                    {/* Summary stats */}
                    <div className="grid grid-cols-3 gap-3 mt-4 pt-3 border-t">
                      <div className="text-center">
                        <p className="text-2xl font-bold">{selectedFacility.total_inspections}</p>
                        <p className="text-xs text-muted-foreground">Inspections</p>
                      </div>
                      <div className="text-center">
                        <p className="text-2xl font-bold text-amber-600">{selectedFacility.total_violations}</p>
                        <p className="text-xs text-muted-foreground">Violations</p>
                      </div>
                      <div className="text-center">
                        <p className="text-sm font-medium">{formatDate(selectedFacility.last_inspection_date)}</p>
                        <p className="text-xs text-muted-foreground">Last Inspection</p>
                      </div>
                    </div>
                  </CardContent>
                </Card>

                {/* Equipment */}
                {selectedEquipment && (
                  <Card className="shadow-sm">
                    <CardHeader className="pb-3">
                      <CardTitle className="flex items-center gap-2 text-base">
                        <Wrench className="h-4 w-4" />
                        Equipment (Latest)
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-sm">
                        {selectedEquipment.pool_capacity_gallons && (
                          <div>
                            <span className="text-muted-foreground">Pool Capacity</span>
                            <p className="font-medium">{selectedEquipment.pool_capacity_gallons.toLocaleString()} gal</p>
                          </div>
                        )}
                        {selectedEquipment.flow_rate_gpm && (
                          <div>
                            <span className="text-muted-foreground">Flow Rate</span>
                            <p className="font-medium">{selectedEquipment.flow_rate_gpm} GPM</p>
                          </div>
                        )}
                        {selectedEquipment.filter_pump_1_make && (
                          <div>
                            <span className="text-muted-foreground">Pump</span>
                            <p className="font-medium">
                              {selectedEquipment.filter_pump_1_make}
                              {selectedEquipment.filter_pump_1_model ? ` ${selectedEquipment.filter_pump_1_model}` : ""}
                              {selectedEquipment.filter_pump_1_hp ? ` (${selectedEquipment.filter_pump_1_hp} HP)` : ""}
                            </p>
                          </div>
                        )}
                        {selectedEquipment.filter_1_make && (
                          <div>
                            <span className="text-muted-foreground">Filter</span>
                            <p className="font-medium">
                              {selectedEquipment.filter_1_make}
                              {selectedEquipment.filter_1_model ? ` ${selectedEquipment.filter_1_model}` : ""}
                              {selectedEquipment.filter_1_type ? ` (${selectedEquipment.filter_1_type})` : ""}
                            </p>
                          </div>
                        )}
                        {selectedEquipment.sanitizer_1_details && (
                          <div>
                            <span className="text-muted-foreground">Sanitizer</span>
                            <p className="font-medium">{selectedEquipment.sanitizer_1_details}</p>
                          </div>
                        )}
                        {selectedEquipment.main_drain_model && (
                          <div>
                            <span className="text-muted-foreground">Main Drain</span>
                            <p className="font-medium">{selectedEquipment.main_drain_model}</p>
                          </div>
                        )}
                      </div>
                    </CardContent>
                  </Card>
                )}

                {/* Inspection History */}
                <Card className="shadow-sm">
                  <CardHeader className="pb-3">
                    <CardTitle className="flex items-center gap-2 text-base">
                      <ClipboardCheck className="h-4 w-4" />
                      Inspection History
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="p-0">
                    <div className="max-h-[500px] overflow-y-auto">
                      {selectedFacility.inspections.map((insp) => (
                        <div key={insp.id} className="border-b last:border-b-0">
                          <button
                            className="w-full px-4 py-3 text-left hover:bg-slate-50 dark:hover:bg-slate-900 flex items-center justify-between"
                            onClick={() =>
                              setExpandedInspection(
                                expandedInspection === insp.id ? null : insp.id
                              )
                            }
                          >
                            <div className="flex items-center gap-3">
                              <div>
                                <p className="text-sm font-medium">
                                  {formatDate(insp.inspection_date)}
                                </p>
                                <p className="text-xs text-muted-foreground">
                                  {insp.inspection_type || "Inspection"}
                                  {insp.inspector_name ? ` — ${insp.inspector_name}` : ""}
                                </p>
                              </div>
                            </div>
                            <div className="flex items-center gap-2">
                              {insp.major_violations > 0 && (
                                <Badge variant="destructive" className="text-xs">
                                  {insp.major_violations} major
                                </Badge>
                              )}
                              {insp.total_violations > 0 && (
                                <Badge variant="secondary" className="text-xs">
                                  {insp.total_violations} violations
                                </Badge>
                              )}
                              {insp.closure_status && insp.closure_status !== "operational" && (
                                <Badge variant="destructive" className="text-xs">
                                  {insp.closure_status}
                                </Badge>
                              )}
                              {expandedInspection === insp.id ? (
                                <ChevronUp className="h-4 w-4 text-muted-foreground" />
                              ) : (
                                <ChevronDown className="h-4 w-4 text-muted-foreground" />
                              )}
                            </div>
                          </button>

                          {expandedInspection === insp.id && (
                            <InspectionDetail inspection={insp} />
                          )}
                        </div>
                      ))}
                      {selectedFacility.inspections.length === 0 && (
                        <p className="text-center py-8 text-muted-foreground text-sm">
                          No inspection records
                        </p>
                      )}
                    </div>
                  </CardContent>
                </Card>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function InspectionDetail({ inspection }: { inspection: EMDInspection }) {
  const [violations, setViolations] = useState<EMDViolation[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // If violations are already loaded (from the detail response), use them
    if (inspection.violations && inspection.violations.length > 0) {
      setViolations(inspection.violations);
      setLoading(false);
      return;
    }

    // Otherwise load them separately (when only count is available)
    setViolations([]);
    setLoading(false);
  }, [inspection]);

  return (
    <div className="px-4 pb-4 space-y-3">
      {/* Pool specs */}
      {(inspection.pool_capacity_gallons || inspection.flow_rate_gpm) && (
        <div className="flex gap-4 text-xs">
          {inspection.pool_capacity_gallons && (
            <span className="text-muted-foreground">
              Capacity: <span className="font-medium text-foreground">{inspection.pool_capacity_gallons.toLocaleString()} gal</span>
            </span>
          )}
          {inspection.flow_rate_gpm && (
            <span className="text-muted-foreground">
              Flow: <span className="font-medium text-foreground">{inspection.flow_rate_gpm} GPM</span>
            </span>
          )}
        </div>
      )}

      {/* Notes */}
      {inspection.report_notes && (
        <div className="bg-muted/50 rounded-md p-3">
          <p className="text-xs text-muted-foreground whitespace-pre-line line-clamp-4">
            {inspection.report_notes}
          </p>
        </div>
      )}

      {/* Violations */}
      {violations.length > 0 ? (
        <div className="space-y-2">
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
            Violations
          </p>
          {violations.map((v) => (
            <div
              key={v.id}
              className={`rounded-md p-3 text-sm ${
                v.is_major_violation
                  ? "bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800"
                  : "bg-muted/50"
              }`}
            >
              <div className="flex items-start gap-2">
                {v.is_major_violation && (
                  <AlertTriangle className="h-3.5 w-3.5 text-red-500 mt-0.5 flex-shrink-0" />
                )}
                <div className="min-w-0">
                  <p className="font-medium text-sm">
                    {v.violation_code && (
                      <span className="text-muted-foreground mr-1">{v.violation_code}.</span>
                    )}
                    {v.shorthand_summary || v.violation_title || "Violation"}
                  </p>
                  {v.observations && (
                    <p className="text-xs text-muted-foreground mt-1 line-clamp-3">
                      {v.observations}
                    </p>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        loading && (
          <div className="flex items-center justify-center py-4">
            <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
          </div>
        )
      )}
    </div>
  );
}
