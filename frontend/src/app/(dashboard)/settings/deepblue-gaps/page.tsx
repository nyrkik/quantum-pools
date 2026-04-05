"use client";

import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import { PageLayout } from "@/components/layout/page-layout";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import { Loader2, Check, Bot, Database, HelpCircle } from "lucide-react";

interface KnowledgeGap {
  id: string;
  user_question: string;
  resolution: "meta_tool" | "unresolved";
  sql_query: string | null;
  reason: string | null;
  result_row_count: number | null;
  reviewed: boolean;
  promoted_to_tool: string | null;
  created_at: string;
}

export default function DeepBlueGapsPage() {
  const [gaps, setGaps] = useState<KnowledgeGap[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<"unreviewed" | "all">("unreviewed");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = filter === "unreviewed" ? "?reviewed=false" : "";
      const data = await api.get<{ gaps: KnowledgeGap[] }>(`/v1/deepblue/knowledge-gaps${params}`);
      setGaps(data.gaps);
    } catch {
      toast.error("Failed to load gaps");
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => { load(); }, [load]);

  const markReviewed = async (gapId: string, promotedTo?: string) => {
    try {
      const resp = await fetch(`/api/v1/deepblue/knowledge-gaps/${gapId}/review`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ promoted_to_tool: promotedTo || null }),
      });
      if (!resp.ok) throw new Error("Failed");
      toast.success("Marked reviewed");
      load();
    } catch {
      toast.error("Failed to update");
    }
  };

  // Group by similar questions (simple prefix match)
  const groupedGaps = gaps.reduce((acc, gap) => {
    const key = gap.user_question.toLowerCase().slice(0, 50);
    if (!acc[key]) acc[key] = [];
    acc[key].push(gap);
    return acc;
  }, {} as Record<string, KnowledgeGap[]>);

  const groups = Object.entries(groupedGaps).sort((a, b) => b[1].length - a[1].length);

  return (
    <PageLayout title="DeepBlue Knowledge Gaps">
      <div className="space-y-4">
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant={filter === "unreviewed" ? "default" : "outline"}
            onClick={() => setFilter("unreviewed")}
          >
            Unreviewed
          </Button>
          <Button
            size="sm"
            variant={filter === "all" ? "default" : "outline"}
            onClick={() => setFilter("all")}
          >
            All
          </Button>
        </div>

        {loading ? (
          <div className="flex justify-center py-12">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : groups.length === 0 ? (
          <Card className="shadow-sm">
            <CardContent className="py-12 text-center text-muted-foreground">
              <Bot className="h-10 w-10 mx-auto mb-2 opacity-30" />
              <p>No knowledge gaps. DeepBlue is answering everything with existing tools.</p>
            </CardContent>
          </Card>
        ) : (
          groups.map(([key, groupGaps]) => {
            const first = groupGaps[0];
            const count = groupGaps.length;
            return (
              <Card key={key} className="shadow-sm">
                <CardHeader className="pb-2">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      <CardTitle className="text-sm flex items-center gap-2">
                        {first.resolution === "meta_tool" ? (
                          <Database className="h-4 w-4 text-blue-600 shrink-0" />
                        ) : (
                          <HelpCircle className="h-4 w-4 text-amber-600 shrink-0" />
                        )}
                        <span className="truncate">{first.user_question}</span>
                      </CardTitle>
                    </div>
                    <Badge variant={first.resolution === "meta_tool" ? "default" : "outline"}>
                      {count > 1 ? `${count}×` : first.resolution === "meta_tool" ? "meta" : "unresolved"}
                    </Badge>
                  </div>
                </CardHeader>
                <CardContent className="space-y-2">
                  {groupGaps.map((gap) => (
                    <div key={gap.id} className="text-xs border-l-2 border-muted pl-3 py-1 space-y-1">
                      {count > 1 && (
                        <p className="text-muted-foreground">{gap.user_question}</p>
                      )}
                      {gap.sql_query && (
                        <pre className="bg-muted/50 rounded p-2 overflow-x-auto text-[10px] font-mono">{gap.sql_query}</pre>
                      )}
                      {gap.resolution === "meta_tool" && gap.reason && (
                        <p className="text-muted-foreground italic">Reason: {gap.reason}</p>
                      )}
                      {gap.resolution === "unresolved" && gap.reason && (
                        <p className="text-muted-foreground italic">Response: {gap.reason.slice(0, 200)}</p>
                      )}
                      <div className="flex items-center justify-between text-muted-foreground">
                        <span>{new Date(gap.created_at).toLocaleString()}</span>
                        {!gap.reviewed && (
                          <Button size="sm" variant="ghost" className="h-6 text-[10px]" onClick={() => markReviewed(gap.id)}>
                            <Check className="h-3 w-3 mr-1" /> Mark reviewed
                          </Button>
                        )}
                        {gap.reviewed && gap.promoted_to_tool && (
                          <Badge variant="secondary" className="text-[10px]">→ {gap.promoted_to_tool}</Badge>
                        )}
                      </div>
                    </div>
                  ))}
                </CardContent>
              </Card>
            );
          })
        )}
      </div>
    </PageLayout>
  );
}
