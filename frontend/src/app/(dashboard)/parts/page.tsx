"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { api, getBackendOrigin } from "@/lib/api";
import { toast } from "sonner";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Overlay, OverlayContent, OverlayHeader, OverlayTitle, OverlayBody } from "@/components/ui/overlay";
import {
  Search,
  ExternalLink,
  Loader2,
  Package,
  RefreshCw,
  ChevronRight,
  ChevronDown,
  Filter,
  Cog,
  Flame,
  Droplets,
  Cpu,
  Wrench,
  Beaker,
  CircleDot,
  Settings2,
  Box,
  Clock,
} from "lucide-react";
import { formatCurrency } from "@/lib/format";
import { usePermissions } from "@/lib/permissions";
import { VendorSettingsSheet } from "@/components/parts/vendor-settings-sheet";

// --- Types ---

type CatalogType = "equipment" | "parts" | "chemicals" | "services";

interface CatalogPart {
  id: string;
  sku: string;
  name: string;
  brand: string | null;
  category: string | null;
  subcategory: string | null;
  description: string | null;
  image_url: string | null;
  product_url: string | null;
  is_chemical: boolean;
  for_equipment_id?: string | null;
}

interface EquipmentEntry {
  id: string;
  canonical_name: string;
  equipment_type: string;
  manufacturer: string | null;
  model_number: string | null;
  category: string | null;
  image_url: string | null;
  specs: Record<string, unknown> | null;
  parts?: CatalogPart[];
}

interface ServiceItem {
  id: string;
  name: string;
  default_amount: number;
  category: string;
  is_taxable: boolean;
}

interface Vendor {
  id: string;
  name: string;
  provider_type: string;
  search_url_template: string | null;
}

// --- Constants ---

const CATEGORY_ICONS: Record<string, React.ElementType> = {
  "Pumps & Motors": Cog, "Filters & Media": Filter, "Heaters": Flame,
  "Water Treatment": Droplets, "Cleaners & Sweeps": Wrench,
  "Plumbing & Fittings": Settings2, "Automation & Electrical": Cpu,
  "Seals & O-Rings": CircleDot, "Safety & Compliance": Box,
  "Chemicals": Beaker,
  "time": Clock, "chemical": Beaker, "material": Package, "other": Box,
};

const EQUIP_TYPE_ICONS: Record<string, React.ElementType> = {
  pump: Cog, filter: Filter, heater: Flame, chlorinator: Droplets,
  automation: Cpu, booster_pump: Cog, jet_pump: Cog, chemical_feeder: Droplets, equipment: Box,
};

const EQUIP_TYPE_LABELS: Record<string, string> = {
  pump: "Pumps", filter: "Filters", heater: "Heaters", chlorinator: "Chlorinators",
  automation: "Automation", booster_pump: "Booster Pumps", jet_pump: "Jet Pumps",
  chemical_feeder: "Chemical Feeders", equipment: "Other Equipment",
};

const PARTS_ORDER = [
  "Pumps & Motors", "Filters & Media", "Heaters", "Water Treatment",
  "Cleaners & Sweeps", "Plumbing & Fittings", "Automation & Electrical",
  "Seals & O-Rings", "Safety & Compliance",
];

const EQUIP_ORDER = ["pump", "filter", "heater", "chlorinator", "automation", "booster_pump", "jet_pump", "chemical_feeder", "equipment"];

const SERVICE_CATEGORY_LABELS: Record<string, string> = {
  time: "Labor & Time", chemical: "Chemical Service", material: "Materials", other: "Other",
};

function getCategoryIcon(cat: string) {
  return CATEGORY_ICONS[cat] || Package;
}

// --- Main Page ---

export default function CatalogPage() {
  const perms = usePermissions();
  const backendOrigin = getBackendOrigin();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [activeType, setActiveType] = useState<CatalogType>("equipment");
  const [query, setQuery] = useState("");
  const [searchResults, setSearchResults] = useState<CatalogPart[]>([]);
  const [equipSearchResults, setEquipSearchResults] = useState<EquipmentEntry[]>([]);
  const [searching, setSearching] = useState(false);
  const [categories, setCategories] = useState<{ name: string; count: number }[]>([]);
  const [vendors, setVendors] = useState<Vendor[]>([]);
  const [stats, setStats] = useState<{ total: number } | null>(null);
  const [discovering, setDiscovering] = useState(false);
  const [expandedCategory, setExpandedCategory] = useState<string | null>(null);
  const [categoryParts, setCategoryParts] = useState<Record<string, CatalogPart[]>>({});
  const [categoryEquipment, setCategoryEquipment] = useState<Record<string, EquipmentEntry[]>>({});
  const [loadingCategory, setLoadingCategory] = useState<string | null>(null);
  const [activeSubcategory, setActiveSubcategory] = useState<string | null>(null);
  const [services, setServices] = useState<ServiceItem[]>([]);
  const [selectedEquipId, setSelectedEquipId] = useState<string | null>(null);
  const [loadingData, setLoadingData] = useState(true);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(null);

  useEffect(() => {
    setExpandedCategory(null);
    setCategoryParts({});
    setCategoryEquipment({});
    setQuery("");
    setSearchResults([]);
    setEquipSearchResults([]);
    setLoadingData(true);

    if (activeType === "equipment") {
      api.get<EquipmentEntry[]>("/v1/equipment-catalog/search?limit=500")
        .then((entries) => {
          // Group by equipment_type
          const groups: Record<string, number> = {};
          entries.forEach((e) => {
            groups[e.equipment_type] = (groups[e.equipment_type] || 0) + 1;
          });
          const sorted = EQUIP_ORDER.filter((t) => groups[t]).map((t) => ({ name: t, count: groups[t] }));
          setCategories(sorted);
          setStats({ total: entries.length });

          // Pre-load all equipment by type
          const byType: Record<string, EquipmentEntry[]> = {};
          entries.forEach((e) => {
            (byType[e.equipment_type] = byType[e.equipment_type] || []).push(e);
          });
          setCategoryEquipment(byType);
        })
        .catch(() => {})
        .finally(() => setLoadingData(false));
    } else if (activeType === "parts") {
      Promise.all([
        api.get<string[]>("/v1/parts/categories"),
        api.get<Vendor[]>("/v1/vendors"),
        api.get<{ total: number; by_vendor: Record<string, number> }>("/v1/parts/stats"),
      ]).then(([cats, vends, st]) => {
        const filtered = cats.filter(c => PARTS_ORDER.includes(c));
        const sorted = [...filtered].sort((a, b) => PARTS_ORDER.indexOf(a) - PARTS_ORDER.indexOf(b));
        setCategories(sorted.map(c => ({ name: c, count: 0 })));
        setVendors(vends);
        setStats(st);
        sorted.forEach(c => {
          api.get<CatalogPart[]>(`/v1/parts/search?category=${encodeURIComponent(c)}&limit=500`)
            .then(parts => setCategories(prev => prev.map(cat => cat.name === c ? { ...cat, count: parts.length } : cat)))
            .catch(() => {});
        });
      }).catch(() => {}).finally(() => setLoadingData(false));
    } else if (activeType === "chemicals") {
      api.get<CatalogPart[]>("/v1/parts/search?category=Chemicals&limit=500")
        .then(parts => {
          const groups: Record<string, number> = {};
          parts.forEach(p => { const sub = p.subcategory || "General"; groups[sub] = (groups[sub] || 0) + 1; });
          setCategories(Object.entries(groups).sort(([, a], [, b]) => b - a).map(([name, count]) => ({ name, count })));
          setCategoryParts(prev => {
            const byGroup: Record<string, CatalogPart[]> = {};
            parts.forEach(p => { const sub = p.subcategory || "General"; (byGroup[sub] = byGroup[sub] || []).push(p); });
            return { ...prev, ...byGroup };
          });
          setStats({ total: parts.length });
        })
        .catch(() => {}).finally(() => setLoadingData(false));
    } else if (activeType === "services") {
      api.get<ServiceItem[]>("/v1/charge-templates")
        .then(items => {
          setServices(items);
          const groups: Record<string, number> = {};
          items.forEach(s => { const cat = SERVICE_CATEGORY_LABELS[s.category] || "Other"; groups[cat] = (groups[cat] || 0) + 1; });
          setCategories(Object.entries(groups).map(([name, count]) => ({ name, count })));
          setStats({ total: items.length });
        })
        .catch(() => {}).finally(() => setLoadingData(false));
    }
  }, [activeType]);

  // Unified search
  const doSearch = useCallback(async (q: string) => {
    if (!q.trim()) { setSearchResults([]); setEquipSearchResults([]); return; }
    setSearching(true);
    try {
      if (activeType === "equipment") {
        const data = await api.get<EquipmentEntry[]>(`/v1/equipment-catalog/search?q=${encodeURIComponent(q)}&limit=20`);
        setEquipSearchResults(data);
        // Also search parts to show in results
        const parts = await api.get<CatalogPart[]>(`/v1/parts/search?q=${encodeURIComponent(q)}&limit=20`);
        setSearchResults(parts);
      } else {
        const data = await api.get<CatalogPart[]>(`/v1/parts/search?q=${encodeURIComponent(q)}&limit=40`);
        setSearchResults(data);
      }
    } catch { toast.error("Search failed"); }
    finally { setSearching(false); }
  }, [activeType]);

  useEffect(() => {
    if (activeType === "services") return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => doSearch(query), 300);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [query, doSearch, activeType]);

  const toggleCategory = async (category: string) => {
    if (expandedCategory === category) { setExpandedCategory(null); setActiveSubcategory(null); return; }
    setExpandedCategory(category);
    setActiveSubcategory(null);
    if (activeType === "parts" && !categoryParts[category]) {
      setLoadingCategory(category);
      try {
        const parts = await api.get<CatalogPart[]>(`/v1/parts/search?category=${encodeURIComponent(category)}&limit=500`);
        setCategoryParts(prev => ({ ...prev, [category]: parts }));
      } catch { toast.error("Failed to load"); }
      finally { setLoadingCategory(null); }
    }
  };

  const handleDiscover = async () => {
    setDiscovering(true);
    try {
      const result = await api.post<{ new_models_found: number; parts_discovered: number }>("/v1/parts/discover");
      if (result.new_models_found === 0) toast.info("Catalog is up to date");
      else toast.success(`${result.parts_discovered} parts discovered from ${result.new_models_found} new models`);
      window.location.reload();
    } catch { toast.error("Discovery failed"); }
    finally { setDiscovering(false); }
  };

  const isSearching = query.trim().length > 0;

  return (
    <div className="space-y-4 sm:space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Catalog</h1>
          {stats && <p className="text-sm text-muted-foreground">{stats.total} items</p>}
        </div>
        <div className="flex items-center gap-2">
          {(perms.role === "owner" || perms.role === "admin") && (
            <Button variant="ghost" size="icon" onClick={() => setSettingsOpen(true)}>
              <Settings2 className="h-4 w-4" />
            </Button>
          )}
          {(activeType === "parts" || activeType === "equipment") && (
            <Button variant="outline" size="sm" onClick={handleDiscover} disabled={discovering} className="h-8 text-xs">
              {discovering ? <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5 mr-1.5" />}
              {discovering ? "Discovering..." : "Update Catalog"}
            </Button>
          )}
        </div>
      </div>

      {/* Type toggle */}
      <div className="flex gap-1 bg-muted p-1 rounded-lg w-fit">
        {(["equipment", "parts", "chemicals", "services"] as CatalogType[]).map(type => (
          <button
            key={type}
            onClick={() => setActiveType(type)}
            className={`px-3 py-1.5 text-sm rounded-md transition-colors ${
              activeType === type ? "bg-background shadow-sm font-medium" : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {type.charAt(0).toUpperCase() + type.slice(1)}
          </button>
        ))}
      </div>

      {/* Search bar */}
      {activeType !== "services" && (
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input value={query} onChange={(e) => setQuery(e.target.value)}
            placeholder={activeType === "equipment" ? "Search equipment or parts..." : `Search ${activeType}...`}
            className="pl-9 h-10 text-sm" />
        </div>
      )}

      {/* Loading */}
      {loadingData && (
        <div className="flex justify-center py-8"><Loader2 className="h-5 w-5 animate-spin text-muted-foreground" /></div>
      )}

      {/* Search results */}
      {!loadingData && isSearching && activeType !== "services" && (
        <div>
          {searching ? (
            <div className="flex justify-center py-8"><Loader2 className="h-5 w-5 animate-spin text-muted-foreground" /></div>
          ) : (equipSearchResults.length === 0 && searchResults.length === 0) ? (
            <div className="text-center py-8 space-y-3">
              <Package className="h-8 w-8 text-muted-foreground mx-auto" />
              <p className="text-sm text-muted-foreground">No results for &quot;{query}&quot;</p>
            </div>
          ) : (
            <div className="space-y-3">
              {/* Equipment results */}
              {equipSearchResults.length > 0 && (
                <div>
                  <p className="text-xs text-muted-foreground mb-2 uppercase tracking-wide font-medium">Equipment ({equipSearchResults.length})</p>
                  <div className="space-y-1">
                    {equipSearchResults.map(entry => (
                      <EquipmentRow key={entry.id} entry={entry} backendOrigin={backendOrigin} onClick={() => setSelectedEquipId(entry.id)} />
                    ))}
                  </div>
                </div>
              )}
              {/* Parts results */}
              {searchResults.length > 0 && (
                <div>
                  {activeType === "equipment" && <p className="text-xs text-muted-foreground mb-2 uppercase tracking-wide font-medium">Parts ({searchResults.length})</p>}
                  <div className="space-y-1">
                    {searchResults.map(part => (
                      <PartRow key={part.id} part={part} backendOrigin={backendOrigin} onViewEquipment={part.for_equipment_id ? () => setSelectedEquipId(part.for_equipment_id!) : undefined} />
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Equipment browse */}
      {!loadingData && !isSearching && activeType === "equipment" && (
        <div className="space-y-1">
          {categories.map(cat => {
            const Icon = EQUIP_TYPE_ICONS[cat.name] || Box;
            const label = EQUIP_TYPE_LABELS[cat.name] || cat.name;
            const isExpanded = expandedCategory === cat.name;
            const entries = categoryEquipment[cat.name] || [];
            return (
              <div key={cat.name} className="border rounded-lg overflow-hidden">
                <button onClick={() => setExpandedCategory(isExpanded ? null : cat.name)}
                  className="w-full flex items-center justify-between px-4 py-3 hover:bg-muted/50 transition-colors">
                  <div className="flex items-center gap-3">
                    <Icon className="h-4 w-4 text-muted-foreground" />
                    <span className="text-sm font-medium">{label}</span>
                    <Badge variant="secondary" className="text-[10px] h-5 px-2">{cat.count}</Badge>
                  </div>
                  {isExpanded ? <ChevronDown className="h-4 w-4 text-muted-foreground" /> : <ChevronRight className="h-4 w-4 text-muted-foreground" />}
                </button>
                {isExpanded && (
                  <div className="border-t bg-muted/20 divide-y">
                    {entries.length === 0 ? (
                      <p className="text-xs text-muted-foreground text-center py-4">No items</p>
                    ) : (
                      entries.map(entry => (
                        <EquipmentRow key={entry.id} entry={entry} backendOrigin={backendOrigin} onClick={() => setSelectedEquipId(entry.id)} />
                      ))
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Parts browse */}
      {!loadingData && !isSearching && activeType === "parts" && (
        <div className="space-y-1">
          {categories.map(cat => {
            const Icon = getCategoryIcon(cat.name);
            const isExpanded = expandedCategory === cat.name;
            const isLoading = loadingCategory === cat.name;
            const parts = categoryParts[cat.name] || [];
            return (
              <div key={cat.name} className="border rounded-lg overflow-hidden">
                <button onClick={() => toggleCategory(cat.name)}
                  className="w-full flex items-center justify-between px-4 py-3 hover:bg-muted/50 transition-colors">
                  <div className="flex items-center gap-3">
                    <Icon className="h-4 w-4 text-muted-foreground" />
                    <span className="text-sm font-medium">{cat.name}</span>
                    {cat.count > 0 && <Badge variant="secondary" className="text-[10px] h-5 px-2">{cat.count}</Badge>}
                  </div>
                  {isLoading ? <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                    : isExpanded ? <ChevronDown className="h-4 w-4 text-muted-foreground" />
                    : <ChevronRight className="h-4 w-4 text-muted-foreground" />}
                </button>
                {isExpanded && (() => {
                  const subcats = [...new Set(parts.map(p => p.subcategory).filter(Boolean))] as string[];
                  const filtered = activeSubcategory ? parts.filter(p => p.subcategory === activeSubcategory) : parts;
                  return (
                    <div className="border-t bg-muted/20">
                      {parts.length === 0 && !isLoading
                        ? <p className="text-xs text-muted-foreground text-center py-4">No items</p>
                        : <>
                            {subcats.length > 1 && (
                              <div className="flex gap-1.5 px-4 py-2 overflow-x-auto border-b">
                                <button onClick={() => setActiveSubcategory(null)}
                                  className={`px-2.5 py-1 text-xs rounded-full whitespace-nowrap transition-colors ${!activeSubcategory ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground hover:text-foreground"}`}>
                                  All ({parts.length})
                                </button>
                                {subcats.sort().map(sub => (
                                  <button key={sub} onClick={() => setActiveSubcategory(activeSubcategory === sub ? null : sub)}
                                    className={`px-2.5 py-1 text-xs rounded-full whitespace-nowrap transition-colors ${activeSubcategory === sub ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground hover:text-foreground"}`}>
                                    {sub} ({parts.filter(p => p.subcategory === sub).length})
                                  </button>
                                ))}
                              </div>
                            )}
                            <div className="divide-y">{filtered.map(part => (
                              <PartRow key={part.id} part={part} backendOrigin={backendOrigin} onViewEquipment={part.for_equipment_id ? () => setSelectedEquipId(part.for_equipment_id!) : undefined} />
                            ))}</div>
                          </>}
                    </div>
                  );
                })()}
              </div>
            );
          })}
        </div>
      )}

      {/* Chemicals browse */}
      {!loadingData && !isSearching && activeType === "chemicals" && (
        <div className="space-y-1">
          {categories.map(cat => {
            const isExpanded = expandedCategory === cat.name;
            const parts = categoryParts[cat.name] || [];
            return (
              <div key={cat.name} className="border rounded-lg overflow-hidden">
                <button onClick={() => setExpandedCategory(isExpanded ? null : cat.name)}
                  className="w-full flex items-center justify-between px-4 py-3 hover:bg-muted/50 transition-colors">
                  <div className="flex items-center gap-3">
                    <Beaker className="h-4 w-4 text-muted-foreground" />
                    <span className="text-sm font-medium">{cat.name}</span>
                    <Badge variant="secondary" className="text-[10px] h-5 px-2">{cat.count}</Badge>
                  </div>
                  {isExpanded ? <ChevronDown className="h-4 w-4 text-muted-foreground" /> : <ChevronRight className="h-4 w-4 text-muted-foreground" />}
                </button>
                {isExpanded && (
                  <div className="border-t bg-muted/20 divide-y">
                    {parts.map(part => (
                      <PartRow key={part.id} part={part} backendOrigin={backendOrigin} />
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Services view */}
      {activeType === "services" && (
        <div className="space-y-1">
          {categories.map(cat => {
            const Icon = getCategoryIcon(Object.entries(SERVICE_CATEGORY_LABELS).find(([, v]) => v === cat.name)?.[0] || "other");
            const items = services.filter(s => (SERVICE_CATEGORY_LABELS[s.category] || "Other") === cat.name);
            const isExpanded = expandedCategory === cat.name;
            return (
              <div key={cat.name} className="border rounded-lg overflow-hidden">
                <button onClick={() => setExpandedCategory(isExpanded ? null : cat.name)}
                  className="w-full flex items-center justify-between px-4 py-3 hover:bg-muted/50 transition-colors">
                  <div className="flex items-center gap-3">
                    <Icon className="h-4 w-4 text-muted-foreground" />
                    <span className="text-sm font-medium">{cat.name}</span>
                    <Badge variant="secondary" className="text-[10px] h-5 px-2">{cat.count}</Badge>
                  </div>
                  {isExpanded ? <ChevronDown className="h-4 w-4 text-muted-foreground" /> : <ChevronRight className="h-4 w-4 text-muted-foreground" />}
                </button>
                {isExpanded && (
                  <div className="border-t bg-muted/20 divide-y">
                    {items.map(s => (
                      <div key={s.id} className="flex items-center justify-between px-4 py-2.5">
                        <div>
                          <p className="text-sm font-medium">{s.name}</p>
                          <p className="text-xs text-muted-foreground">{s.is_taxable ? "Taxable" : "Non-taxable"}</p>
                        </div>
                        <span className="text-sm font-medium">{formatCurrency(s.default_amount)}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
          {services.length === 0 && (
            <p className="text-sm text-muted-foreground text-center py-8">No services configured. Add them in Settings.</p>
          )}
        </div>
      )}

      {/* Equipment detail overlay */}
      <EquipmentDetailOverlay
        equipmentId={selectedEquipId}
        open={!!selectedEquipId}
        onClose={() => setSelectedEquipId(null)}
        backendOrigin={backendOrigin}
      />

      <VendorSettingsSheet open={settingsOpen} onOpenChange={setSettingsOpen} />
    </div>
  );
}

// --- Equipment Row ---

function EquipmentRow({ entry, backendOrigin, onClick }: { entry: EquipmentEntry; backendOrigin: string; onClick: () => void }) {
  return (
    <div className="flex items-center gap-3 px-4 py-2.5 hover:bg-muted/30 transition-colors cursor-pointer" onClick={onClick}>
      <div className="flex-shrink-0 h-10 w-10 rounded bg-muted/50 flex items-center justify-center overflow-hidden">
        {entry.image_url ? (
          <img src={`${backendOrigin}${entry.image_url}`} alt="" className="h-full w-full object-contain" />
        ) : (
          <Package className="h-4 w-4 text-muted-foreground" />
        )}
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium truncate">{entry.canonical_name}</p>
        <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
          {entry.manufacturer && <span>{entry.manufacturer}</span>}
          {entry.model_number && entry.model_number !== "?" && <span className="font-mono bg-muted px-1 rounded">{entry.model_number}</span>}
          {entry.category && <span>· {entry.category}</span>}
        </div>
      </div>
      <ChevronRight className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
    </div>
  );
}

// --- Part Row ---

function PartRow({ part, backendOrigin, onViewEquipment }: { part: CatalogPart; backendOrigin: string; onViewEquipment?: () => void }) {
  return (
    <div className="flex items-center gap-3 px-4 py-2.5 hover:bg-muted/30 transition-colors">
      <div className="flex-shrink-0 h-8 w-8 rounded bg-muted flex items-center justify-center overflow-hidden">
        {part.image_url ? (
          <img src={part.image_url.startsWith("/uploads") ? `${backendOrigin}${part.image_url}` : part.image_url} alt="" className="h-full w-full object-cover" />
        ) : (
          <Package className="h-3.5 w-3.5 text-muted-foreground" />
        )}
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium truncate">{part.name}</p>
        <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
          <span className="font-mono bg-muted px-1 rounded">{part.sku}</span>
          {part.brand && <span>{part.brand}</span>}
        </div>
      </div>
      {onViewEquipment && (
        <Button variant="ghost" size="sm" className="text-xs h-7 shrink-0" onClick={onViewEquipment}>
          View Equipment
        </Button>
      )}
      {part.product_url && (
        <a href={part.product_url} target="_blank" rel="noopener noreferrer" className="p-1.5 text-muted-foreground hover:text-primary shrink-0">
          <ExternalLink className="h-3.5 w-3.5" />
        </a>
      )}
    </div>
  );
}

// --- Equipment Detail Overlay ---

function EquipmentDetailOverlay({ equipmentId, open, onClose, backendOrigin }: { equipmentId: string | null; open: boolean; onClose: () => void; backendOrigin: string }) {
  const [data, setData] = useState<EquipmentEntry | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open || !equipmentId) return;
    setLoading(true);
    setData(null);
    api.get<EquipmentEntry>(`/v1/equipment-catalog/${equipmentId}`)
      .then(setData)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [open, equipmentId]);

  return (
    <Overlay open={open} onOpenChange={(o) => { if (!o) onClose(); }}>
      <OverlayContent className="max-w-md">
        <OverlayHeader>
          <OverlayTitle>{data?.canonical_name || "Equipment"}</OverlayTitle>
        </OverlayHeader>
        <OverlayBody className="space-y-4">
          {loading ? (
            <div className="flex justify-center py-8"><Loader2 className="h-5 w-5 animate-spin text-muted-foreground" /></div>
          ) : !data ? (
            <p className="text-sm text-muted-foreground text-center py-8">Not found</p>
          ) : (
            <>
              {data.image_url && (
                <div className="flex justify-center">
                  <img src={`${backendOrigin}${data.image_url}`} alt={data.canonical_name} className="h-32 w-32 object-contain rounded-md bg-muted/30" />
                </div>
              )}

              <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
                {[
                  { label: "Manufacturer", value: data.manufacturer },
                  { label: "Model #", value: data.model_number !== "?" ? data.model_number : null },
                  { label: "Category", value: data.category },
                  ...(data.specs ? Object.entries(data.specs).map(([k, v]) => ({ label: k.toUpperCase(), value: String(v) })) : []),
                ].filter(d => d.value).map(d => (
                  <div key={d.label} className="contents">
                    <span className="text-muted-foreground text-xs">{d.label}</span>
                    <span className="font-medium text-xs">{d.value}</span>
                  </div>
                ))}
              </div>

              {data.parts && data.parts.length > 0 && (
                <div className="space-y-2">
                  <p className="text-[10px] text-muted-foreground uppercase tracking-wide font-medium">Compatible Parts ({data.parts.length})</p>
                  <div className="space-y-1.5">
                    {data.parts.map(p => (
                      <div key={p.id} className="flex items-start justify-between text-xs border rounded-md p-2 bg-muted/30">
                        <div className="min-w-0">
                          <p className="font-medium truncate">{p.name}</p>
                          <div className="flex items-center gap-2 text-muted-foreground mt-0.5">
                            {p.brand && <span>{p.brand}</span>}
                            {p.sku && <span>SKU: {p.sku}</span>}
                          </div>
                          {p.category && <Badge variant="secondary" className="text-[9px] px-1 mt-1">{p.category}</Badge>}
                        </div>
                        {p.product_url && (
                          <a href={p.product_url} target="_blank" rel="noopener noreferrer" className="text-muted-foreground hover:text-primary shrink-0 ml-2">
                            <ExternalLink className="h-3.5 w-3.5" />
                          </a>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {(!data.parts || data.parts.length === 0) && (
                <p className="text-xs text-muted-foreground italic text-center">No parts linked yet</p>
              )}
            </>
          )}
        </OverlayBody>
      </OverlayContent>
    </Overlay>
  );
}
