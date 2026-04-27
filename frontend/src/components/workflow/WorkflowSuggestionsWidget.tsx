"use client";

/**
 * Phase 6 dashboard widget — surfaces staged workflow_observer
 * meta-proposals (workflow_config + inbox_rule entity types) using the
 * existing ProposalCardMini. Renders nothing for users without the
 * `workflow.review` permission.
 *
 * Data source: GET /v1/proposals?agent_type=workflow_observer&status=staged
 * "Never suggest this": PUT /v1/workflow/observer-mutes/{detector_id}
 *   (the detector_id is parsed from input_context's `[detector_id]`
 *    prefix; falls back to a generic mute label when absent).
 */

import { useCallback, useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Loader2, Sparkles, BellOff } from "lucide-react";
import { api } from "@/lib/api";
import { listProposals, type Proposal } from "@/lib/proposals";
import { usePermissions } from "@/lib/permissions";
import { ProposalCardMini } from "@/components/proposals/ProposalCardMini";


function detectorIdFromContext(input_context: string | null | undefined): string | null {
  if (!input_context || !input_context.startsWith("[")) return null;
  const end = input_context.indexOf("]");
  if (end <= 1) return null;
  return input_context.slice(1, end).trim() || null;
}


export function WorkflowSuggestionsWidget() {
  const perms = usePermissions();
  const canReview = perms.can("workflow.review");

  const [items, setItems] = useState<Proposal[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [muting, setMuting] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!canReview) return;
    setLoading(true);
    setError(null);
    try {
      const res = await listProposals({
        agentType: "workflow_observer",
        status: "staged",
        limit: 5,
      });
      setItems(res.items);
    } catch (e) {
      setError((e as Error).message || "Failed to load workflow suggestions");
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [canReview]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  if (!canReview) return null;

  async function muteDetector(detector_id: string) {
    setMuting(detector_id);
    try {
      await api.put<unknown>(
        `/v1/workflow/observer-mutes/${encodeURIComponent(detector_id)}`,
        {},
      );
      await refresh();
    } catch (e) {
      setError((e as Error).message || "Mute failed");
    } finally {
      setMuting(null);
    }
  }

  return (
    <Card className="shadow-sm">
      <CardHeader className="bg-primary text-primary-foreground px-4 py-2.5">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <Sparkles className="h-4 w-4 opacity-70" />
          Workflow suggestions
          {items && items.length > 0 ? (
            <Badge variant="secondary" className="ml-auto">{items.length}</Badge>
          ) : null}
        </CardTitle>
      </CardHeader>
      <CardContent className="p-4 space-y-3">
        {loading ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading suggestions…
          </div>
        ) : error ? (
          <div className="text-sm text-destructive">{error}</div>
        ) : !items || items.length === 0 ? (
          <div className="text-sm text-muted-foreground">
            No workflow suggestions yet. The product learns from your activity over time.
          </div>
        ) : (
          <div className="space-y-3">
            {items.map((p) => {
              const detector_id = detectorIdFromContext(p.input_context);
              return (
                <div key={p.id} className="space-y-2">
                  <ProposalCardMini
                    proposal={p}
                    onResolved={() => refresh()}
                    onError={(e) => setError(e.message)}
                  />
                  {detector_id ? (
                    <div className="flex justify-end">
                      <Button
                        variant="ghost"
                        size="sm"
                        disabled={muting === detector_id}
                        onClick={() => muteDetector(detector_id)}
                        className="text-xs text-muted-foreground hover:text-destructive"
                      >
                        {muting === detector_id ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" />
                        ) : (
                          <BellOff className="h-3.5 w-3.5 mr-1" />
                        )}
                        Never suggest this
                      </Button>
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
