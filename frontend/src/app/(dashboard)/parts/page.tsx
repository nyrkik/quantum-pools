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
  ShoppingCart,
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
  Zap,
  Settings2,
  Box,
} from "lucide-react";
import { LogPurchaseForm } from "@/components/parts/log-purchase-form";

interface CatalogPart {
  id: string;
  vendor_provider: string;
  sku: string;
  name: string;
  brand: string | null;
  category: string | null;
  subcategory: string | null;
  description: string | null;
  image_url: string | null;
  product_url: string | null;
  is_chemical: boolean;
  estimated_price?: number | null;
}

interface Vendor {
  id: string;
  name: string;
  provider_type: string;
  search_url_template: string | null;
}

interface CategoryInfo {
  name: string;
  count: number;
}

const CATEGORY_ICONS: Record<string, React.ElementType> = {
  "Equipment": Cog,
  "Filters": Filter,
  "Chemicals": Beaker,
  "Parts & Repair": Wrench,
  "Tools & Supplies": Settings2,
};

const CATEGORY_ORDER = ["Equipment", "Filters", "Chemicals", "Parts & Repair", "Tools & Supplies"];

function getCategoryIcon(category: string) {
  return CATEGORY_ICONS[category] || Package;
}

export default function PartsPage() {
  const [query, setQuery] = useState("");
  const [searchResults, setSearchResults] = useState<CatalogPart[]>([]);
  const [searching, setSearching] = useState(false);
  const [categories, setCategories] = useState<CategoryInfo[]>([]);
  const [vendors, setVendors] = useState<Vendor[]>([]);
  const [stats, setStats] = useState<{ total: number; by_vendor: Record<string, number> } | null>(null);
  const [discovering, setDiscovering] = useState(false);
  const [expandedCategory, setExpandedCategory] = useState<string | null>(null);
  const [categoryParts, setCategoryParts] = useState<Record<string, CatalogPart[]>>({});
  const [loadingCategory, setLoadingCategory] = useState<string | null>(null);
  const [purchasePart, setPurchasePart] = useState<CatalogPart | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(null);

  // Load initial data
  useEffect(() => {
    Promise.all([
      api.get<string[]>("/v1/parts/categories"),
      api.get<Vendor[]>("/v1/vendors"),
      api.get<{ total: number; by_vendor: Record<string, number> }>("/v1/parts/stats"),
    ]).then(([cats, vends, st]) => {
      // Get counts per category
      const catPromises = cats.map(async (c) => {
        const parts = await api.get<CatalogPart[]>(`/v1/parts/search?category=${encodeURIComponent(c)}&limit=0`).catch(() => []);
        return { name: c, count: parts.length };
      });
      // Actually, the search endpoint doesn't return count separately. Let's use a different approach.
      // Just load all parts per category count from search with limit=200
      const sorted = [...cats].sort((a, b) => {
        const ai = CATEGORY_ORDER.indexOf(a);
        const bi = CATEGORY_ORDER.indexOf(b);
        return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
      });
      setCategories(sorted.map(c => ({ name: c, count: 0 })));
      setVendors(vends);
      setStats(st);

      // Get actual counts
      cats.forEach(c => {
        api.get<CatalogPart[]>(`/v1/parts/search?category=${encodeURIComponent(c)}&limit=200`)
          .then(parts => {
            setCategories(prev => prev.map(cat => cat.name === c ? { ...cat, count: parts.length } : cat));
          })
          .catch(() => {});
      });
    }).catch(() => {});
  }, []);

  // Search
  const doSearch = useCallback(async (q: string) => {
    if (!q.trim()) {
      setSearchResults([]);
      return;
    }
    setSearching(true);
    try {
      const data = await api.get<CatalogPart[]>(`/v1/parts/search?q=${encodeURIComponent(q)}&limit=40`);
      setSearchResults(data);
    } catch {
      toast.error("Search failed");
    } finally {
      setSearching(false);
    }
  }, []);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => doSearch(query), 300);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [query, doSearch]);

  // Expand/collapse category
  const toggleCategory = async (category: string) => {
    if (expandedCategory === category) {
      setExpandedCategory(null);
      return;
    }
    setExpandedCategory(category);
    if (!categoryParts[category]) {
      setLoadingCategory(category);
      try {
        const parts = await api.get<CatalogPart[]>(`/v1/parts/search?category=${encodeURIComponent(category)}&limit=200`);
        setCategoryParts(prev => ({ ...prev, [category]: parts }));
      } catch {
        toast.error("Failed to load parts");
      } finally {
        setLoadingCategory(null);
      }
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
      const result = await api.post<{
        models_scanned: number; new_models_found: number; parts_discovered: number; errors: number;
      }>("/v1/parts/discover");
      if (result.new_models_found === 0) {
        toast.info("Catalog is up to date");
      } else {
        toast.success(`${result.parts_discovered} parts discovered from ${result.new_models_found} new models`);
      }
      // Refresh
      window.location.reload();
    } catch {
      toast.error("Catalog discovery failed");
    } finally {
      setDiscovering(false);
    }
  };

  const isSearching = query.trim().length > 0;

  return (
    <div className="space-y-4 sm:space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Parts Catalog</h1>
          {stats && (
            <p className="text-sm text-muted-foreground">{stats.total} parts</p>
          )}
        </div>
        <Button variant="outline" size="sm" onClick={handleDiscover} disabled={discovering} className="h-8 text-xs">
          {discovering ? <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5 mr-1.5" />}
          {discovering ? "Discovering..." : "Update Catalog"}
        </Button>
      </div>

      {/* Search bar */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search parts by name, SKU, or brand..."
          className="pl-9 h-10 text-sm"
        />
      </div>

      {/* Log purchase form (inline) */}
      {purchasePart && (
        <Card className="border-l-4 border-primary shadow-sm">
          <CardContent className="pt-4">
            <div className="flex items-center justify-between mb-3">
              <p className="text-sm font-medium">Log Purchase: {purchasePart.name}</p>
              <Button variant="ghost" size="sm" className="h-6 text-xs" onClick={() => setPurchasePart(null)}>Cancel</Button>
            </div>
            <LogPurchaseForm
              onPurchaseLogged={() => { setPurchasePart(null); }}
              onCancel={() => setPurchasePart(null)}
            />
          </CardContent>
        </Card>
      )}

      {/* Search results (when searching) */}
      {isSearching && (
        <div>
          {searching ? (
            <div className="flex justify-center py-8">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : searchResults.length === 0 ? (
            <div className="text-center py-8 space-y-3">
              <Package className="h-8 w-8 text-muted-foreground mx-auto" />
              <p className="text-sm text-muted-foreground">No parts found for &quot;{query}&quot;</p>
              <Button variant="outline" size="sm" onClick={() => { const url = getSearchUrl(query); if (url) window.open(url, "_blank"); }}>
                <ExternalLink className="h-3.5 w-3.5 mr-1.5" /> Search on SCP
              </Button>
            </div>
          ) : (
            <div className="space-y-1">
              <p className="text-xs text-muted-foreground mb-2">{searchResults.length} results</p>
              {searchResults.map((part) => (
                <PartRow key={part.id} part={part} onLogPurchase={() => setPurchasePart(part)} getSearchUrl={getSearchUrl} />
              ))}
            </div>
          )}
        </div>
      )}

      {/* Category browse (default view) */}
      {!isSearching && (
        <div className="space-y-1">
          {categories.map((cat) => {
            const Icon = getCategoryIcon(cat.name);
            const isExpanded = expandedCategory === cat.name;
            const isLoading = loadingCategory === cat.name;
            const parts = categoryParts[cat.name] || [];

            return (
              <div key={cat.name} className="border rounded-lg overflow-hidden">
                <button
                  onClick={() => toggleCategory(cat.name)}
                  className="w-full flex items-center justify-between px-4 py-3 hover:bg-muted/50 transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <Icon className="h-4 w-4 text-muted-foreground" />
                    <span className="text-sm font-medium">{cat.name}</span>
                    {cat.count > 0 && (
                      <Badge variant="secondary" className="text-[10px] h-5 px-2">{cat.count}</Badge>
                    )}
                  </div>
                  {isLoading ? (
                    <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                  ) : isExpanded ? (
                    <ChevronDown className="h-4 w-4 text-muted-foreground" />
                  ) : (
                    <ChevronRight className="h-4 w-4 text-muted-foreground" />
                  )}
                </button>

                {isExpanded && (
                  <div className="border-t bg-muted/20">
                    {parts.length === 0 && !isLoading ? (
                      <p className="text-xs text-muted-foreground text-center py-4">No parts in this category</p>
                    ) : (
                      <div className="divide-y">
                        {parts.map((part) => (
                          <PartRow key={part.id} part={part} onLogPurchase={() => setPurchasePart(part)} getSearchUrl={getSearchUrl} />
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function PartRow({ part, onLogPurchase, getSearchUrl }: {
  part: CatalogPart;
  onLogPurchase: () => void;
  getSearchUrl: (q: string) => string | null;
}) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="px-4 py-2.5 hover:bg-muted/30 transition-colors">
      <div className="flex items-center gap-3 cursor-pointer" onClick={() => setExpanded(!expanded)}>
        <div className="flex-shrink-0 h-8 w-8 rounded bg-muted flex items-center justify-center overflow-hidden">
          {part.image_url ? (
            <img src={part.image_url} alt="" className="h-full w-full object-cover" />
          ) : (
            <Package className="h-3.5 w-3.5 text-muted-foreground" />
          )}
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium truncate">{part.name}</p>
          <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
            <span className="font-mono bg-muted px-1 rounded">{part.sku}</span>
            {part.brand && <span>{part.brand}</span>}
            {part.subcategory && <span>· {part.subcategory}</span>}
          </div>
        </div>
        <ChevronDown className={`h-3.5 w-3.5 text-muted-foreground transition-transform flex-shrink-0 ${expanded ? "rotate-180" : ""}`} />
      </div>

      {expanded && (
        <div className="ml-11 mt-2 space-y-2 pb-1">
          {part.description && (
            <p className="text-xs text-muted-foreground">{part.description}</p>
          )}
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" className="h-7 text-xs" onClick={(e) => { e.stopPropagation(); onLogPurchase(); }}>
              <ShoppingCart className="h-3 w-3 mr-1" /> Log Purchase
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="h-7 text-xs"
              onClick={(e) => {
                e.stopPropagation();
                const url = part.product_url || getSearchUrl(part.name);
                if (url) window.open(url, "_blank");
              }}
            >
              <ExternalLink className="h-3 w-3 mr-1" /> Buy Online
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
