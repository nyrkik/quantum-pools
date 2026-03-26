"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Search, ExternalLink, ShoppingCart, Loader2, Package } from "lucide-react";

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

interface PartsSearchDialogProps {
  open: boolean;
  onClose: () => void;
  onSelectPart?: (part: CatalogPart) => void;
  onLogPurchase?: (part: CatalogPart) => void;
  jobId?: string;
  propertyId?: string;
  waterFeatureId?: string;
}

export function PartsSearchDialog({
  open,
  onClose,
  onSelectPart,
  onLogPurchase,
  jobId,
  propertyId,
  waterFeatureId,
}: PartsSearchDialogProps) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<CatalogPart[]>([]);
  const [loading, setLoading] = useState(false);
  const [categories, setCategories] = useState<string[]>([]);
  const [brands, setBrands] = useState<string[]>([]);
  const [selectedCategory, setSelectedCategory] = useState<string>("");
  const [selectedBrand, setSelectedBrand] = useState<string>("");
  const [vendors, setVendors] = useState<Vendor[]>([]);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Load categories, brands, and vendors on open
  useEffect(() => {
    if (!open) return;
    Promise.all([
      api.get<string[]>("/v1/parts/categories"),
      api.get<string[]>("/v1/parts/brands"),
      api.get<Vendor[]>("/v1/vendors"),
    ]).then(([cats, brds, vends]) => {
      setCategories(cats);
      setBrands(brds);
      setVendors(vends);
    }).catch(() => {});

    // Initial search (show all)
    doSearch("", "", "");

    // Focus input
    setTimeout(() => inputRef.current?.focus(), 100);
  }, [open]);

  const doSearch = useCallback(async (q: string, cat: string, brand: string) => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.set("q", q);
      params.set("limit", "30");
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

  // Debounced search on query change
  useEffect(() => {
    if (!open) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      doSearch(query, selectedCategory, selectedBrand);
    }, 300);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query, selectedCategory, selectedBrand, open, doSearch]);

  const getScpSearchUrl = (q: string): string | null => {
    const scp = vendors.find((v) => v.provider_type === "scp");
    if (!scp?.search_url_template) return null;
    return scp.search_url_template.replace("{query}", encodeURIComponent(q));
  };

  const handleReset = () => {
    setQuery("");
    setSelectedCategory("");
    setSelectedBrand("");
    setResults([]);
  };

  const handleClose = () => {
    handleReset();
    onClose();
  };

  return (
    <Dialog open={open} onOpenChange={(v) => !v && handleClose()}>
      <DialogContent className="max-w-2xl max-h-[85vh] flex flex-col p-0">
        <DialogHeader className="px-4 pt-4 pb-0">
          <DialogTitle className="text-base flex items-center gap-2">
            <Package className="h-4 w-4" />
            Search Parts Catalog
          </DialogTitle>
        </DialogHeader>

        {/* Search input */}
        <div className="px-4 pt-3 space-y-2">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              ref={inputRef}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search by name, SKU, brand..."
              className="pl-9"
            />
          </div>

          {/* Filters */}
          <div className="flex gap-2">
            <Select value={selectedCategory || "all"} onValueChange={(v) => setSelectedCategory(v === "all" ? "" : v)}>
              <SelectTrigger className="h-8 text-xs flex-1">
                <SelectValue placeholder="All Categories" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Categories</SelectItem>
                {categories.map((c) => (
                  <SelectItem key={c} value={c}>{c}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={selectedBrand || "all"} onValueChange={(v) => setSelectedBrand(v === "all" ? "" : v)}>
              <SelectTrigger className="h-8 text-xs flex-1">
                <SelectValue placeholder="All Brands" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Brands</SelectItem>
                {brands.map((b) => (
                  <SelectItem key={b} value={b}>{b}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        {/* Results */}
        <ScrollArea className="flex-1 min-h-0 px-4 pb-4">
          {loading ? (
            <div className="flex justify-center py-8">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : results.length === 0 ? (
            <div className="text-center py-8 space-y-3">
              <p className="text-sm text-muted-foreground">
                {query ? "No parts found" : "Enter a search term to find parts"}
              </p>
              {query && (
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
                  Search on SCP
                </Button>
              )}
            </div>
          ) : (
            <div className="space-y-1.5 pt-2">
              {results.map((part) => (
                <div
                  key={part.id}
                  className="flex items-start gap-3 rounded-md border p-2.5 hover:bg-accent/50 transition-colors"
                >
                  {/* Image or placeholder */}
                  <div className="flex-shrink-0 h-12 w-12 rounded bg-muted flex items-center justify-center overflow-hidden">
                    {part.image_url ? (
                      <img src={part.image_url} alt="" className="h-full w-full object-cover" />
                    ) : (
                      <Package className="h-5 w-5 text-muted-foreground" />
                    )}
                  </div>

                  {/* Info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium truncate">{part.name}</span>
                    </div>
                    <div className="flex items-center gap-2 mt-0.5 flex-wrap">
                      <span className="text-[10px] text-muted-foreground bg-muted px-1.5 py-0.5 rounded font-mono">
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
                      {part.is_chemical && (
                        <Badge variant="outline" className="text-[10px] h-4 px-1.5 border-amber-400 text-amber-600">
                          Chemical
                        </Badge>
                      )}
                    </div>
                    {part.description && (
                      <p className="text-[11px] text-muted-foreground mt-0.5 line-clamp-1">
                        {part.description}
                      </p>
                    )}
                  </div>

                  {/* Actions */}
                  <div className="flex flex-col gap-1 flex-shrink-0">
                    {onSelectPart && (
                      <Button
                        variant="outline"
                        size="sm"
                        className="h-7 text-xs"
                        onClick={() => {
                          onSelectPart(part);
                          handleClose();
                        }}
                      >
                        Select
                      </Button>
                    )}
                    {onLogPurchase && (
                      <Button
                        variant="outline"
                        size="sm"
                        className="h-7 text-xs"
                        onClick={() => {
                          onLogPurchase(part);
                          handleClose();
                        }}
                      >
                        <ShoppingCart className="h-3 w-3 mr-1" />
                        Log
                      </Button>
                    )}
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 text-xs text-muted-foreground"
                      onClick={() => {
                        const url = part.product_url || getScpSearchUrl(part.name);
                        if (url) window.open(url, "_blank");
                      }}
                    >
                      <ExternalLink className="h-3 w-3 mr-1" />
                      SCP
                    </Button>
                  </div>
                </div>
              ))}

              {/* Fallback search on SCP */}
              {query && (
                <div className="pt-2 text-center">
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-xs text-muted-foreground"
                    onClick={() => {
                      const url = getScpSearchUrl(query);
                      if (url) window.open(url, "_blank");
                    }}
                  >
                    <ExternalLink className="h-3 w-3 mr-1" />
                    Search &quot;{query}&quot; on pool360.com
                  </Button>
                </div>
              )}
            </div>
          )}
        </ScrollArea>
      </DialogContent>
    </Dialog>
  );
}
