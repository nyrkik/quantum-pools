"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { FolderSymlink, Link2, Loader2, Plus, Search, Unlink2 } from "lucide-react";
import { toast } from "sonner";

export type LinkableEntityType =
  | "job"
  | "thread"
  | "invoice"
  | "internal_thread"
  | "deepblue_conversation";

interface CaseOption {
  id: string;
  case_number: string;
  title: string;
  status: string;
  customer_name?: string | null;
}

interface Props {
  entityType: LinkableEntityType;
  entityId: string;
  /** Customer hint — scopes the default suggestions to this customer's cases. */
  customerId?: string | null;
  /** Current case (if any) — shows as a pill with an unlink X. */
  currentCaseId?: string | null;
  currentCaseNumber?: string | null;
  currentCaseTitle?: string | null;
  /** Called after a successful link/unlink. Parent should refetch state. */
  onChange?: () => void;
  /** Size hint for the trigger button. Defaults to sm. */
  size?: "sm" | "default";
}

/**
 * LinkCasePicker — shared component for attaching/detaching an entity to a
 * ServiceCase. Used on invoice, thread, job, internal thread, and DeepBlue
 * detail views. See docs/entity-connections-plan.md.
 */
export function LinkCasePicker({
  entityType,
  entityId,
  customerId,
  currentCaseId,
  currentCaseNumber,
  currentCaseTitle,
  onChange,
  size = "sm",
}: Props) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [suggested, setSuggested] = useState<CaseOption[]>([]);
  const [searchResults, setSearchResults] = useState<CaseOption[]>([]);
  const [loading, setLoading] = useState(false);
  const [working, setWorking] = useState(false);
  const [creatingNew, setCreatingNew] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Preload open cases for this customer when the picker opens.
  useEffect(() => {
    if (!open) return;
    setQuery("");
    setSearchResults([]);
    setCreatingNew(false);
    setNewTitle("");
    const run = async () => {
      setLoading(true);
      try {
        const params = new URLSearchParams({ limit: "10" });
        if (customerId) params.set("customer_id", customerId);
        const data = await api.get<{ items: CaseOption[] }>(`/v1/cases?${params}`);
        setSuggested(data.items.filter((c) => c.id !== currentCaseId));
      } catch {
        setSuggested([]);
      } finally {
        setLoading(false);
      }
    };
    void run();
  }, [open, customerId, currentCaseId]);

  const doSearch = useCallback(async (q: string) => {
    if (q.trim().length < 2) {
      setSearchResults([]);
      return;
    }
    setLoading(true);
    try {
      const params = new URLSearchParams({ search: q.trim(), limit: "15" });
      const data = await api.get<{ items: CaseOption[] }>(`/v1/cases?${params}`);
      setSearchResults(data.items.filter((c) => c.id !== currentCaseId));
    } catch {
      setSearchResults([]);
    } finally {
      setLoading(false);
    }
  }, [currentCaseId]);

  const handleQuery = (v: string) => {
    setQuery(v);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => void doSearch(v), 250);
  };

  const linkToCase = async (caseId: string) => {
    setWorking(true);
    try {
      await api.post(`/v1/cases/${caseId}/link`, { type: entityType, id: entityId });
      toast.success("Linked to case");
      setOpen(false);
      onChange?.();
    } catch (e) {
      const err = e as { message?: string };
      toast.error(err.message || "Failed to link");
    } finally {
      setWorking(false);
    }
  };

  const unlink = async () => {
    if (!currentCaseId) return;
    setWorking(true);
    try {
      const params = new URLSearchParams({ entity_type: entityType, entity_id: entityId });
      await api.delete(`/v1/cases/${currentCaseId}/link?${params}`);
      toast.success("Unlinked");
      onChange?.();
    } catch (e) {
      const err = e as { message?: string };
      toast.error(err.message || "Failed to unlink");
    } finally {
      setWorking(false);
    }
  };

  const createAndLink = async () => {
    const title = newTitle.trim() || (query.trim() || "New Case");
    setWorking(true);
    try {
      const created = await api.post<{ id: string; case_number: string }>("/v1/cases", {
        title,
        customer_id: customerId || undefined,
      });
      await api.post(`/v1/cases/${created.id}/link`, { type: entityType, id: entityId });
      toast.success(`Linked to new ${created.case_number}`);
      setOpen(false);
      onChange?.();
    } catch (e) {
      const err = e as { message?: string };
      toast.error(err.message || "Failed to create case");
    } finally {
      setWorking(false);
    }
  };

  const visibleResults = query.trim().length >= 2 ? searchResults : suggested;

  // Render: attached pill OR "Link to case" trigger.
  // Unlink lives INSIDE the picker popover (not as a standalone X next to
  // the pill) — a top-right X iconographically reads as "close this panel"
  // and was getting misclicked as exit when it's actually destructive
  // (FB-48). Deliberate action: tap Link2 → "Unlink from case".
  if (currentCaseId && currentCaseNumber) {
    return (
      <div className="inline-flex items-center gap-1">
        <a
          href={`/cases/${currentCaseId}`}
          className="inline-flex items-center gap-1.5 rounded-md border bg-muted/30 hover:bg-muted/60 px-2 py-1 text-xs text-foreground transition-colors"
        >
          <FolderSymlink className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="font-medium">{currentCaseNumber}</span>
          {currentCaseTitle && (
            <span className="text-muted-foreground truncate max-w-[200px]">
              {currentCaseTitle}
            </span>
          )}
        </a>
        <Popover open={open} onOpenChange={setOpen}>
          <PopoverTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6 text-muted-foreground hover:text-foreground"
              disabled={working}
              title="Change or unlink case"
            >
              <Link2 className="h-3.5 w-3.5" />
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-96 p-0" align="start">
            {renderPickerContent()}
          </PopoverContent>
        </Popover>
      </div>
    );
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          size={size}
          className="gap-1.5 text-muted-foreground"
          disabled={working}
        >
          <Link2 className="h-3.5 w-3.5" />
          Link to case
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-96 p-0" align="start">
        {renderPickerContent()}
      </PopoverContent>
    </Popover>
  );

  function renderPickerContent() {
    if (creatingNew) {
      return (
        <div className="p-3 space-y-2">
          <div className="text-xs font-medium text-muted-foreground">
            Create new case
          </div>
          <Input
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            placeholder="Case title (e.g., Pool motor replacement)"
            className="h-8 text-sm"
            autoFocus
          />
          <div className="flex items-center justify-end gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setCreatingNew(false)}
              disabled={working}
            >
              Cancel
            </Button>
            <Button
              size="sm"
              onClick={createAndLink}
              disabled={working || !newTitle.trim()}
            >
              {working && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              Create &amp; link
            </Button>
          </div>
        </div>
      );
    }

    return (
      <div>
        <div className="p-2 border-b">
          <div className="relative">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
            <Input
              value={query}
              onChange={(e) => handleQuery(e.target.value)}
              placeholder={customerId ? "Search all cases…" : "Search cases…"}
              className="h-8 pl-7 text-sm"
              autoFocus
            />
          </div>
        </div>
        <div className="max-h-72 overflow-y-auto">
          {loading && visibleResults.length === 0 ? (
            <div className="flex items-center justify-center py-6">
              <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
            </div>
          ) : visibleResults.length === 0 ? (
            <div className="px-3 py-4 text-xs text-muted-foreground text-center">
              {query.trim().length >= 2
                ? "No matching cases"
                : customerId
                ? "No open cases for this customer"
                : "Type to search"}
            </div>
          ) : (
            <>
              {query.trim().length < 2 && customerId && (
                <div className="px-3 pt-2 pb-1 text-[10px] uppercase tracking-wide text-muted-foreground">
                  Cases for this customer
                </div>
              )}
              {visibleResults.map((c) => (
                <button
                  key={c.id}
                  type="button"
                  className="w-full text-left px-3 py-2 hover:bg-muted/50 text-sm border-b last:border-b-0 disabled:opacity-50"
                  onClick={() => linkToCase(c.id)}
                  disabled={working}
                >
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-xs text-muted-foreground">
                      {c.case_number}
                    </span>
                    <span className="truncate flex-1">{c.title}</span>
                    <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
                      {c.status.replace(/_/g, " ")}
                    </span>
                  </div>
                  {c.customer_name && (
                    <div className="text-xs text-muted-foreground mt-0.5 truncate">
                      {c.customer_name}
                    </div>
                  )}
                </button>
              ))}
            </>
          )}
        </div>
        <div className="border-t">
          <button
            type="button"
            className="w-full text-left px-3 py-2 hover:bg-muted/50 text-sm flex items-center gap-1.5 text-muted-foreground"
            onClick={() => {
              setCreatingNew(true);
              setNewTitle(query);
            }}
            disabled={working}
          >
            <Plus className="h-3.5 w-3.5" />
            Create new case{customerId ? " for this customer" : ""}
          </button>
          {currentCaseId && (
            <button
              type="button"
              className="w-full text-left px-3 py-2 hover:bg-destructive/10 text-sm flex items-center gap-1.5 text-destructive border-t"
              onClick={async () => {
                await unlink();
                setOpen(false);
              }}
              disabled={working}
            >
              <Unlink2 className="h-3.5 w-3.5" />
              Unlink from {currentCaseNumber}
            </button>
          )}
        </div>
      </div>
    );
  }
}
