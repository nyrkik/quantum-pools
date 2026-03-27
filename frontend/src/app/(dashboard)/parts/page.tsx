"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
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

// --- Types ---

type CatalogType = "parts" | "chemicals" | "services";

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

const PARTS_ORDER = [
  "Pumps & Motors", "Filters & Media", "Heaters", "Water Treatment",
  "Cleaners & Sweeps", "Plumbing & Fittings", "Automation & Electrical",
  "Seals & O-Rings", "Safety & Compliance",
];

const SERVICE_CATEGORY_LABELS: Record<string, string> = {
  time: "Labor & Time", chemical: "Chemical Service", material: "Materials", other: "Other",
};

function getCategoryIcon(cat: string) {
  return CATEGORY_ICONS[cat] || Package;
}

// --- Main Page ---

export default function CatalogPage() {
  const [activeType, setActiveType] = useState<CatalogType>("parts");
  const [query, setQuery] = useState("");
  const [searchResults, setSearchResults] = useState<CatalogPart[]>([]);
  const [searching, setSearching] = useState(false);
  const [categories, setCategories] = useState<{ name: string; count: number }[]>([]);
  const [vendors, setVendors] = useState<Vendor[]>([]);
  const [stats, setStats] = useState<{ total: number } | null>(null);
  const [discovering, setDiscovering] = useState(false);
  const [expandedCategory, setExpandedCategory] = useState<string | null>(null);
  const [categoryParts, setCategoryParts] = useState<Record<string, CatalogPart[]>>({});
  const [loadingCategory, setLoadingCategory] = useState<string | null>(null);
  const [activeSubcategory, setActiveSubcategory] = useState<string | null>(null);
  const [services, setServices] = useState<ServiceItem[]>([]);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(null);

  // Load data based on active type
  useEffect(() => {
    setExpandedCategory(null);
    setCategoryParts({});
    setQuery("");
    setSearchResults([]);

    if (activeType === "parts") {
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
      }).catch(() => {});
    } else if (activeType === "chemicals") {
      api.get<CatalogPart[]>("/v1/parts/search?category=Chemicals&limit=500")
        .then(parts => {
          // Group by subcategory
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
        .catch(() => {});
    } else if (activeType === "services") {
      api.get<ServiceItem[]>("/v1/charge-templates")
        .then(items => {
          setServices(items);
          const groups: Record<string, number> = {};
          items.forEach(s => { const cat = SERVICE_CATEGORY_LABELS[s.category] || "Other"; groups[cat] = (groups[cat] || 0) + 1; });
          setCategories(Object.entries(groups).map(([name, count]) => ({ name, count })));
          setStats({ total: items.length });
        })
        .catch(() => {});
    }
  }, [activeType]);

  // Search (parts only)
  const doSearch = useCallback(async (q: string) => {
    if (!q.trim()) { setSearchResults([]); return; }
    setSearching(true);
    try {
      const data = await api.get<CatalogPart[]>(`/v1/parts/search?q=${encodeURIComponent(q)}&limit=40`);
      setSearchResults(data);
    } catch { toast.error("Search failed"); }
    finally { setSearching(false); }
  }, []);

  useEffect(() => {
    if (activeType !== "parts" && activeType !== "chemicals") return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => doSearch(query), 300);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [query, doSearch, activeType]);

  const toggleCategory = async (category: string) => {
    if (expandedCategory === category) { setExpandedCategory(null); setActiveSubcategory(null); return; }
    setExpandedCategory(category);
    setActiveSubcategory(null);
    if (!categoryParts[category]) {
      setLoadingCategory(category);
      try {
        const parts = await api.get<CatalogPart[]>(`/v1/parts/search?category=${encodeURIComponent(category)}&limit=500`);
        setCategoryParts(prev => ({ ...prev, [category]: parts }));
      } catch { toast.error("Failed to load"); }
      finally { setLoadingCategory(null); }
    }
  };

  const getSearchUrl = (q: string): string | null => {
    const scp = vendors.find(v => v.provider_type === "scp");
    if (!scp?.search_url_template) return null;
    return scp.search_url_template.replace("{query}", encodeURIComponent(q));
  };

  const handleDiscover = async () => {
    setDiscovering(true);
    try {
      const result = await api.post<{ new_models_found: number; parts_discovered: number; errors: number }>("/v1/parts/discover");
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
        {activeType === "parts" && (
          <Button variant="outline" size="sm" onClick={handleDiscover} disabled={discovering} className="h-8 text-xs">
            {discovering ? <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5 mr-1.5" />}
            {discovering ? "Discovering..." : "Update Catalog"}
          </Button>
        )}
      </div>

      {/* Type toggle */}
      <div className="flex gap-1 bg-muted p-1 rounded-lg w-fit">
        {(["parts", "chemicals", "services"] as CatalogType[]).map(type => (
          <button
            key={type}
            onClick={() => setActiveType(type)}
            className={`px-4 py-1.5 text-sm rounded-md transition-colors ${
              activeType === type ? "bg-background shadow-sm font-medium" : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {type === "parts" ? "Parts" : type === "chemicals" ? "Chemicals" : "Services"}
          </button>
        ))}
      </div>

      {/* Search bar (parts + chemicals) */}
      {activeType !== "services" && (
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input value={query} onChange={(e) => setQuery(e.target.value)}
            placeholder={`Search ${activeType}...`} className="pl-9 h-10 text-sm" />
        </div>
      )}


      {/* Search results */}
      {isSearching && activeType !== "services" && (
        <div>
          {searching ? (
            <div className="flex justify-center py-8"><Loader2 className="h-5 w-5 animate-spin text-muted-foreground" /></div>
          ) : searchResults.length === 0 ? (
            <div className="text-center py-8 space-y-3">
              <Package className="h-8 w-8 text-muted-foreground mx-auto" />
              <p className="text-sm text-muted-foreground">No results for &quot;{query}&quot;</p>
              {activeType === "parts" && (
                <Button variant="outline" size="sm" onClick={() => { const url = getSearchUrl(query); if (url) window.open(url, "_blank"); }}>
                  <ExternalLink className="h-3.5 w-3.5 mr-1.5" /> Search on SCP
                </Button>
              )}
            </div>
          ) : (
            <div className="space-y-1">
              <p className="text-xs text-muted-foreground mb-2">{searchResults.length} results</p>
              {searchResults.map(part => (
                <PartRow key={part.id} part={part}  getSearchUrl={getSearchUrl} />
              ))}
            </div>
          )}
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
            <p className="text-sm text-muted-foreground text-center py-8">No services configured. Add them in Settings → Charges.</p>
          )}
        </div>
      )}

      {/* Category browse (parts + chemicals, not searching) */}
      {!isSearching && activeType !== "services" && (
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
                  // Get unique subcategories for filter pills
                  const subcats = [...new Set(parts.map(p => p.subcategory).filter(Boolean))] as string[];
                  const filtered = activeSubcategory
                    ? parts.filter(p => p.subcategory === activeSubcategory)
                    : parts;
                  return (
                    <div className="border-t bg-muted/20">
                      {parts.length === 0 && !isLoading
                        ? <p className="text-xs text-muted-foreground text-center py-4">No items</p>
                        : <>
                            {subcats.length > 1 && (
                              <div className="flex gap-1.5 px-4 py-2 overflow-x-auto border-b">
                                <button
                                  onClick={() => setActiveSubcategory(null)}
                                  className={`px-2.5 py-1 text-xs rounded-full whitespace-nowrap transition-colors ${
                                    !activeSubcategory ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground hover:text-foreground"
                                  }`}
                                >
                                  All ({parts.length})
                                </button>
                                {subcats.sort().map(sub => (
                                  <button
                                    key={sub}
                                    onClick={() => setActiveSubcategory(activeSubcategory === sub ? null : sub)}
                                    className={`px-2.5 py-1 text-xs rounded-full whitespace-nowrap transition-colors ${
                                      activeSubcategory === sub ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground hover:text-foreground"
                                    }`}
                                  >
                                    {sub} ({parts.filter(p => p.subcategory === sub).length})
                                  </button>
                                ))}
                              </div>
                            )}
                            <div className="divide-y">{filtered.map(part => (
                              <PartRow key={part.id} part={part} getSearchUrl={getSearchUrl} />
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
    </div>
  );
}

// --- Part Row ---

function PartRow({ part, getSearchUrl }: {
  part: CatalogPart; getSearchUrl: (q: string) => string | null;
}) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="px-4 py-2.5 hover:bg-muted/30 transition-colors">
      <div className="flex items-center gap-3">
        <div className="flex-shrink-0 h-8 w-8 rounded bg-muted flex items-center justify-center overflow-hidden cursor-pointer" onClick={() => setExpanded(!expanded)}>
          {part.image_url ? <img src={part.image_url} alt="" className="h-full w-full object-cover" />
            : <Package className="h-3.5 w-3.5 text-muted-foreground" />}
        </div>
        <div className="flex-1 min-w-0 cursor-pointer" onClick={() => setExpanded(!expanded)}>
          <p className="text-sm font-medium truncate">{part.name}</p>
          <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
            <span className="font-mono bg-muted px-1 rounded">{part.sku}</span>
            {part.brand && <span>{part.brand}</span>}
          </div>
        </div>
        <button
          className="flex-shrink-0 p-1.5 rounded-md text-muted-foreground hover:text-primary hover:bg-muted transition-colors"
          title="Search online"
          onClick={(e) => {
            e.stopPropagation();
            const url = part.product_url || getSearchUrl(part.name);
            if (url) window.open(url, "_blank");
          }}
        >
          <Search className="h-3.5 w-3.5" />
        </button>
      </div>
      {expanded && part.description && (
        <p className="ml-11 mt-1.5 text-xs text-muted-foreground">{part.description}</p>
      )}
    </div>
  );
}
