"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  Search,
  Link2,
  Loader2,
  X,
  Lock,
  ShoppingCart,
} from "lucide-react";
import type { InspectionFacilityListItem, InspectionFacilityDetail, SearchResult } from "./inspection-types";
import { cleanProgramId, formatDate } from "./inspection-constants";

interface FacilityListProps {
  facilities: InspectionFacilityListItem[];
  filteredFacilities: InspectionFacilityListItem[];
  search: string;
  setSearch: (search: string) => void;
  sortBy: string;
  setSortBy: (sort: string) => void;
  statusFilter: "all" | "open" | "closed";
  setStatusFilter: (filter: "all" | "open" | "closed") => void;
  matchFilter: "all" | "matched" | "unmatched";
  setMatchFilter: (filter: "all" | "matched" | "unmatched") => void;
  loading: boolean;
  isFullResearch: boolean;
  selectedFacility: InspectionFacilityDetail | null;
  selectedPermitId: string | null;
  hasDetailOpen: boolean;
  searchMode: boolean;
  searchResults: SearchResult[];
  cart: Set<string>;
  onSelectFacility: (id: string, permitId?: string | null) => void;
  onToggleCart: (facilityId: string) => void;
}

export function FacilityList({
  facilities,
  filteredFacilities,
  search,
  setSearch,
  sortBy,
  setSortBy,
  statusFilter,
  setStatusFilter,
  matchFilter,
  setMatchFilter,
  loading,
  isFullResearch,
  selectedFacility,
  selectedPermitId,
  hasDetailOpen,
  searchMode,
  searchResults,
  cart,
  onSelectFacility,
  onToggleCart,
}: FacilityListProps) {
  return (
    <div className={`${hasDetailOpen ? "lg:col-span-4" : "lg:col-span-12"} min-h-0 flex flex-col`}>
      <Card className="shadow-sm flex-1 flex flex-col min-h-0">
        {/* Search + sort + filters */}
        <div className="p-3 pb-0 shrink-0 space-y-2">
          <div className="flex gap-2">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder={isFullResearch ? "Search all facilities..." : "Search facilities..."}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-9"
              />
            </div>
            <Select value={sortBy} onValueChange={setSortBy}>
              <SelectTrigger className="w-[140px]">
                <SelectValue placeholder="Sort by" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="name">Name</SelectItem>
                <SelectItem value="violations">Violations</SelectItem>
                <SelectItem value="last_inspection">Last Inspected</SelectItem>
                <SelectItem value="status">Status</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-center gap-3 flex-wrap">
            {isFullResearch ? (
              <>
                <div className="flex items-center gap-1">
                  <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground mr-1">Show</span>
                  {([
                    { value: "all" as const, label: "All Facilities" },
                    { value: "matched" as const, label: "My Clients" },
                    { value: "unmatched" as const, label: "Prospects" },
                  ] as const).map((f) => (
                    <Button
                      key={f.value}
                      variant={matchFilter === f.value ? "default" : "outline"}
                      size="sm"
                      className="h-6 px-2 text-[11px]"
                      onClick={() => setMatchFilter(f.value)}
                    >
                      {f.label}
                    </Button>
                  ))}
                </div>
                <div className="flex items-center gap-1">
                  <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground mr-1">Status</span>
                  {([
                    { value: "all" as const, label: "All" },
                    { value: "open" as const, label: "Open" },
                    { value: "closed" as const, label: "Closed" },
                  ] as const).map((f) => (
                    <Button
                      key={f.value}
                      variant={statusFilter === f.value ? "default" : "outline"}
                      size="sm"
                      className="h-6 px-2 text-[11px]"
                      onClick={() => setStatusFilter(f.value)}
                    >
                      {f.label}
                    </Button>
                  ))}
                </div>
              </>
            ) : (
              <>
                <div className="flex items-center gap-1.5">
                  <Badge variant="secondary" className="text-[10px]">My Clients</Badge>
                  <span className="text-[10px] text-muted-foreground">Showing your matched facilities</span>
                </div>
                <div className="flex items-center gap-1">
                  <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground mr-1">Status</span>
                  {([
                    { value: "all" as const, label: "All" },
                    { value: "open" as const, label: "Open" },
                    { value: "closed" as const, label: "Closed" },
                  ] as const).map((f) => (
                    <Button
                      key={f.value}
                      variant={statusFilter === f.value ? "default" : "outline"}
                      size="sm"
                      className="h-6 px-2 text-[11px]"
                      onClick={() => setStatusFilter(f.value)}
                    >
                      {f.label}
                    </Button>
                  ))}
                </div>
              </>
            )}
          </div>
        </div>

        {/* Facility list */}
        <div className="flex-1 flex flex-col min-h-0">
          <div className="flex-1 overflow-y-auto min-h-0">
            {loading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            ) : filteredFacilities.length === 0 ? (
              <div className="text-center py-8 text-sm text-muted-foreground">No facilities found</div>
            ) : (
              <TooltipProvider delayDuration={200}>
                {filteredFacilities.map((f) => {
                  const rowKey = `${f.id}-${f.permit_id || "default"}`;
                  const isSelected = selectedFacility?.id === f.id && selectedPermitId === f.permit_id;
                  return (
                    <button
                      key={rowKey}
                      onClick={() => onSelectFacility(f.id, f.permit_id)}
                      className={`w-full text-left px-3 py-2 text-sm transition-colors border-b border-border/40 ${
                        isSelected
                          ? "bg-accent border-l-3 border-l-primary font-medium"
                          : f.is_closed
                            ? "bg-red-50/50 dark:bg-red-950/10 hover:bg-red-50 dark:hover:bg-red-950/20 border-l-2 border-l-red-400"
                            : "hover:bg-blue-50 dark:hover:bg-blue-950"
                      }`}
                    >
                      {/* Row 1: Name + status */}
                      <div className="flex items-center gap-1.5 min-w-0">
                        <span className="font-medium truncate">{f.name}</span>
                        {f.program_identifier && (
                          <span className="text-[10px] text-muted-foreground shrink-0">{cleanProgramId(f.program_identifier)}</span>
                        )}
                        {f.matched_property_id && (
                          <Link2 className="h-3 w-3 text-green-500 shrink-0" />
                        )}
                        <span className="ml-auto shrink-0">
                          {f.is_closed ? (
                            f.closure_reasons.length > 0 ? (
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <span>
                                    <Badge variant="destructive" className="text-[10px] px-1.5 py-0 cursor-help">
                                      CLOSED
                                    </Badge>
                                  </span>
                                </TooltipTrigger>
                                <TooltipContent side="right" className="max-w-xs">
                                  <ul className="text-xs space-y-0.5">
                                    {f.closure_reasons.map((r, i) => (
                                      <li key={i}>{r}</li>
                                    ))}
                                  </ul>
                                </TooltipContent>
                              </Tooltip>
                            ) : (
                              <Badge variant="destructive" className="text-[10px] px-1.5 py-0">CLOSED</Badge>
                            )
                          ) : null}
                        </span>
                      </div>

                      {/* Row 2: Address + meta */}
                      <div className="flex items-center gap-2 mt-0.5 min-w-0">
                        <span className="text-xs truncate text-muted-foreground">
                          {f.street_address}{f.city ? `, ${f.city}` : ""}
                        </span>
                        <span className="ml-auto flex items-center gap-2 shrink-0">
                          {f.total_violations > 0 && (
                            <Badge
                              variant={f.total_violations > 10 ? "destructive" : "secondary"}
                              className="text-[10px] px-1.5 py-0"
                            >
                              {f.total_violations} viol
                            </Badge>
                          )}
                          <span className="text-[10px] text-muted-foreground">
                            {f.last_inspection_date ? formatDate(f.last_inspection_date) : "—"}
                          </span>
                        </span>
                      </div>
                    </button>
                  );
                })}
              </TooltipProvider>
            )}

            {/* Search results (redacted facilities for non-full-research) */}
            {searchMode && searchResults.filter(r => r.redacted).length > 0 && (
              <>
                <div className="bg-slate-100 dark:bg-slate-800 px-3 py-1.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground flex items-center gap-2">
                  <Search className="h-3 w-3" />
                  <span>Other Facilities</span>
                  <span className="text-muted-foreground/50">— unlock for $0.99 each</span>
                </div>
                {searchResults.filter(r => r.redacted).map((f) => {
                  const inCart = cart.has(f.id);
                  return (
                    <div
                      key={f.id}
                      className="w-full text-left grid grid-cols-[1fr_auto_auto] gap-x-2 items-center px-3 py-2 text-sm border-b border-border/40 bg-muted/30"
                    >
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <Lock className="h-3 w-3 text-muted-foreground shrink-0" />
                          <span className="font-medium truncate">{f.name}</span>
                        </div>
                        <div className="text-xs text-muted-foreground truncate ml-5">
                          {f.city || "Sacramento County"}
                        </div>
                      </div>
                      <div className="flex items-center gap-1.5">
                        {f.total_violations > 0 && (
                          <Badge
                            variant={f.total_violations > 10 ? "destructive" : "secondary"}
                            className="text-[10px] px-1.5 py-0"
                          >
                            {f.total_violations} viol
                          </Badge>
                        )}
                      </div>
                      <Button
                        variant={inCart ? "default" : "outline"}
                        size="sm"
                        className="h-6 px-2 text-[10px]"
                        onClick={() => onToggleCart(f.id)}
                      >
                        {inCart ? (
                          <><X className="h-3 w-3 mr-0.5" />Remove</>
                        ) : (
                          <><ShoppingCart className="h-3 w-3 mr-0.5" />$0.99</>
                        )}
                      </Button>
                    </div>
                  );
                })}
              </>
            )}
          </div>
        </div>

        {/* Footer count */}
        <div className="text-[11px] text-muted-foreground px-3 py-1.5 border-t shrink-0">
          {filteredFacilities.length} of {facilities.length} facilities
          {searchMode && searchResults.filter(r => r.redacted).length > 0 && (
            <span> + {searchResults.filter(r => r.redacted).length} available to unlock</span>
          )}
        </div>
      </Card>
    </div>
  );
}
