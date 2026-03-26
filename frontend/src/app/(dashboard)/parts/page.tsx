"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Search,
  ExternalLink,
  ShoppingCart,
  Loader2,
  Package,
  X,
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
}

interface Vendor {
  id: string;
  name: string;
  provider_type: string;
  search_url_template: string | null;
}

interface RecentPurchase {
  id: string;
  description: string;
  sku: string | null;
  vendor_name: string;
  unit_cost: number;
  quantity: number;
  total_cost: number;
  purchased_at: string;
}

export default function PartsPage() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<CatalogPart[]>([]);
  const [loading, setLoading] = useState(false);
  const [categories, setCategories] = useState<string[]>([]);
  const [brands, setBrands] = useState<string[]>([]);
  const [selectedCategory, setSelectedCategory] = useState<string>("");
  const [selectedBrand, setSelectedBrand] = useState<string>("");
  const [vendors, setVendors] = useState<Vendor[]>([]);
  const [recentPurchases, setRecentPurchases] = useState<RecentPurchase[]>([]);
  const [purchasePart, setPurchasePart] = useState<CatalogPart | null>(null);
  const [stats, setStats] = useState<{ total: number; by_vendor: Record<string, number> } | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Load initial data
  useEffect(() => {
    Promise.all([
      api.get<string[]>("/v1/parts/categories"),
      api.get<string[]>("/v1/parts/brands"),
      api.get<Vendor[]>("/v1/vendors"),
      api.get<RecentPurchase[]>("/v1/part-purchases?limit=10"),
      api.get<{ total: number; by_vendor: Record<string, number> }>("/v1/parts/stats"),
    ]).then(([cats, brds, vends, purchases, st]) => {
      setCategories(cats);
      setBrands(brds);
      setVendors(vends);
      setRecentPurchases(purchases);
      setStats(st);
    }).catch(() => {});
  }, []);

  const doSearch = useCallback(async (q: string, cat: string, brand: string) => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.set("q", q);
      params.set("limit", "40");
      if (cat) params.set("category", cat);
      if (brand) params.set("brand", brand);
      const data = await api.get<CatalogPart[]>(`/v1/parts/search?${params}`);
      setResults(data);
    } catch {
      toast.error("Search failed");
    } finally {
      setLoading(false);
    }
  }, []);

  // Debounced search
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      doSearch(query, selectedCategory, selectedBrand);
    }, 300);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query, selectedCategory, selectedBrand, doSearch]);

  const getScpSearchUrl = (q: string): string | null => {
    const scp = vendors.find((v) => v.provider_type === "scp");
    if (!scp?.search_url_template) return null;
    return scp.search_url_template.replace("{query}", encodeURIComponent(q));
  };

  const clearFilters = () => {
    setSelectedCategory("");
    setSelectedBrand("");
    setQuery("");
  };

  const hasFilters = selectedCategory || selectedBrand;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Parts Catalog</h1>
          {stats && (
            <p className="text-sm text-muted-foreground">
              {stats.total} parts from {Object.keys(stats.by_vendor).length} vendor{Object.keys(stats.by_vendor).length !== 1 ? "s" : ""}
            </p>
          )}
        </div>
      </div>

      {/* Search bar */}
      <div className="space-y-2">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search parts by name, SKU, brand, or description..."
            className="pl-9 h-10 text-sm"
          />
        </div>

        {/* Filter pills */}
        <div className="flex items-center gap-2 flex-wrap">
          <Select
            value={selectedCategory}
            onValueChange={(v) => setSelectedCategory(v === "all" ? "" : v)}
          >
            <SelectTrigger className="h-7 text-xs w-auto min-w-[120px]">
              <SelectValue placeholder="Category" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Categories</SelectItem>
              {categories.map((c) => (
                <SelectItem key={c} value={c}>{c}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select
            value={selectedBrand}
            onValueChange={(v) => setSelectedBrand(v === "all" ? "" : v)}
          >
            <SelectTrigger className="h-7 text-xs w-auto min-w-[120px]">
              <SelectValue placeholder="Brand" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Brands</SelectItem>
              {brands.map((b) => (
                <SelectItem key={b} value={b}>{b}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          {hasFilters && (
            <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={clearFilters}>
              <X className="h-3 w-3 mr-1" /> Clear
            </Button>
          )}
        </div>
      </div>

      {/* Log purchase form (inline when a part is selected) */}
      {purchasePart && (
        <Card className="border-l-4 border-primary shadow-sm">
          <CardContent className="pt-4">
            <div className="flex items-center justify-between mb-3">
              <p className="text-sm font-medium">Log Purchase: {purchasePart.name}</p>
              <Button variant="ghost" size="sm" className="h-6 text-xs" onClick={() => setPurchasePart(null)}>
                Cancel
              </Button>
            </div>
            <LogPurchaseForm
              onPurchaseLogged={() => {
                setPurchasePart(null);
                api.get<RecentPurchase[]>("/v1/part-purchases?limit=10")
                  .then(setRecentPurchases)
                  .catch(() => {});
              }}
              onCancel={() => setPurchasePart(null)}
            />
          </CardContent>
        </Card>
      )}

      {/* Results */}
      {loading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      ) : results.length === 0 && query ? (
        <div className="text-center py-12 space-y-3">
          <Package className="h-10 w-10 text-muted-foreground mx-auto" />
          <p className="text-sm text-muted-foreground">No parts found for &quot;{query}&quot;</p>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              const url = getScpSearchUrl(query);
              if (url) window.open(url, "_blank");
            }}
            disabled={!getScpSearchUrl(query)}
          >
            <ExternalLink className="h-3.5 w-3.5 mr-1.5" />
            Search on SCP / Pool360
          </Button>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {results.map((part) => (
            <Card key={part.id} className="shadow-sm hover:shadow-md transition-shadow">
              <CardContent className="p-3">
                <div className="flex items-start gap-3">
                  <div className="flex-shrink-0 h-12 w-12 rounded bg-muted flex items-center justify-center overflow-hidden">
                    {part.image_url ? (
                      <img src={part.image_url} alt="" className="h-full w-full object-cover" />
                    ) : (
                      <Package className="h-5 w-5 text-muted-foreground" />
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium leading-tight truncate">{part.name}</p>
                    <div className="flex items-center gap-1.5 mt-1 flex-wrap">
                      <span className="text-[10px] text-muted-foreground bg-muted px-1.5 py-0.5 rounded font-mono">
                        {part.sku}
                      </span>
                      {part.brand && (
                        <span className="text-[10px] text-muted-foreground">{part.brand}</span>
                      )}
                    </div>
                  </div>
                </div>

                {/* Category badges */}
                <div className="flex items-center gap-1.5 mt-2 flex-wrap">
                  {part.category && (
                    <Badge variant="secondary" className="text-[10px] h-4 px-1.5">{part.category}</Badge>
                  )}
                  {part.subcategory && (
                    <Badge variant="outline" className="text-[10px] h-4 px-1.5">{part.subcategory}</Badge>
                  )}
                  {part.is_chemical && (
                    <Badge variant="outline" className="text-[10px] h-4 px-1.5 border-amber-400 text-amber-600">Chemical</Badge>
                  )}
                </div>

                {part.description && (
                  <p className="text-[11px] text-muted-foreground mt-1.5 line-clamp-2">{part.description}</p>
                )}

                {/* Actions */}
                <div className="flex items-center gap-1.5 mt-2.5">
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-7 text-xs flex-1"
                    onClick={() => setPurchasePart(part)}
                  >
                    <ShoppingCart className="h-3 w-3 mr-1" />
                    Log Purchase
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 text-xs"
                    onClick={() => {
                      const url = part.product_url || getScpSearchUrl(part.name);
                      if (url) window.open(url, "_blank");
                    }}
                  >
                    <ExternalLink className="h-3 w-3 mr-1" />
                    SCP
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Recent Purchases */}
      {recentPurchases.length > 0 && (
        <div className="space-y-2">
          <h2 className="text-sm font-medium text-muted-foreground">Recent Purchases</h2>
          <Card className="shadow-sm">
            <CardContent className="p-0">
              <div className="divide-y">
                {recentPurchases.map((p) => (
                  <div key={p.id} className="flex items-center justify-between px-3 py-2 text-sm">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-medium truncate">{p.description}</span>
                        {p.sku && (
                          <span className="text-[10px] text-muted-foreground bg-muted px-1 rounded">{p.sku}</span>
                        )}
                      </div>
                      <div className="flex items-center gap-3 text-xs text-muted-foreground">
                        <span>{p.vendor_name}</span>
                        <span>{p.quantity} x ${p.unit_cost.toFixed(2)}</span>
                        <span>{p.purchased_at}</span>
                      </div>
                    </div>
                    <span className="text-sm font-medium">${p.total_cost.toFixed(2)}</span>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
