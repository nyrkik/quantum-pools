"use client";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Bot } from "lucide-react";
import { api } from "@/lib/api";
import { toast } from "sonner";

interface Suggestion {
  id: string;
  action_type: string;
  description: string;
  reasoning: string;
}

interface AiSuggestionBannerProps {
  suggestion: Suggestion;
  onDismiss: () => void;
  onRefresh: () => void;
}

export function AiSuggestionBanner({
  suggestion,
  onDismiss,
  onRefresh,
}: AiSuggestionBannerProps) {
  return (
    <Card className="shadow-sm border-l-4 border-blue-500 bg-blue-50/50 dark:bg-blue-950/20">
      <CardContent className="py-3 px-4">
        <div className="flex items-start gap-3">
          <Bot className="h-4 w-4 text-blue-500 mt-0.5 flex-shrink-0" />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium">Suggested next step</p>
            <p className="text-sm mt-0.5">{suggestion.description}</p>
            <p className="text-xs text-muted-foreground mt-1">
              {suggestion.reasoning}
            </p>
          </div>
          <div className="flex gap-1.5 flex-shrink-0">
            <Button
              size="sm"
              className="h-7"
              onClick={async () => {
                try {
                  await api.put(
                    `/v1/admin/agent-actions/${suggestion.id}`,
                    { status: "open" }
                  );
                  toast.success("Action accepted");
                  onDismiss();
                  onRefresh();
                } catch {
                  toast.error("Failed");
                }
              }}
            >
              Accept
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="h-7"
              onClick={async () => {
                try {
                  await api.put(
                    `/v1/admin/agent-actions/${suggestion.id}`,
                    { status: "cancelled" }
                  );
                  onDismiss();
                  onRefresh();
                } catch {
                  toast.error("Failed");
                }
              }}
            >
              Dismiss
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
