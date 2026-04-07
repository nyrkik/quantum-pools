"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { api, getBackendOrigin } from "@/lib/api";
import { toast } from "sonner";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Search,
  Loader2,
  Package,
  RefreshCw,
  ChevronRight,
  ChevronDown,
  Beaker,
  Box,
  Settings2,
} from "lucide-react";
import { formatCurrency } from "@/lib/format";
import { usePermissions } from "@/lib/permissions";
import { VendorSettingsSheet } from "@/components/parts/vendor-settings-sheet";
import { EquipmentRow } from "@/components/parts/equipment-row";
import { PartRow } from "@/components/parts/part-row";
import { EquipmentDetailOverlay } from "@/components/parts/equipment-detail-overlay";
import {
  type CatalogType,
  type CatalogPart,
  type EquipmentEntry,
  type ServiceItem,
  type Vendor,
  EQUIP_TYPE_ICONS,
  EQUIP_TYPE_LABELS,
  PARTS_ORDER,
  EQUIP_ORDER,
  SERVICE_CATEGORY_LABELS,
  getCategoryIcon,
} from "@/components/parts/catalog-types";

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

