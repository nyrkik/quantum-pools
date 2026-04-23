"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { PageLayout } from "@/components/layout/page-layout";
import { BackButton } from "@/components/ui/back-button";
import { ProposalCard } from "@/components/proposals/ProposalCard";
import { listProposals, type Proposal } from "@/lib/proposals";
import { usePermissions } from "@/lib/permissions";

export default function InboxMatchesPage() {
  const router = useRouter();
  const perms = usePermissions();
  const allowed = perms.role === "owner" || perms.role === "admin";

  const [loading, setLoading] = useState(true);
  const [proposals, setProposals] = useState<Proposal[]>([]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await listProposals({
        entityType: "customer_match_suggestion",
        status: "staged",
        limit: 200,
      });
      setProposals(res.items);
    } catch {
      toast.error("Failed to load suggestions");
      setProposals([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (allowed) load();
  }, [allowed, load]);

  // Role gate: non-owner/admin roles get a 403-ish message, not the queue.
  if (!allowed) {
    return (
      <PageLayout
        title="Customer Match Review"
        secondaryActions={<BackButton fallback="/inbox" label="" />}
      >
        <div className="text-sm text-muted-foreground">
          This queue is visible to owners and admins only.
        </div>
      </PageLayout>
    );
  }

  return (
    <PageLayout
      title="Customer Match Review"
      secondaryActions={<BackButton fallback="/inbox" label="" />}
    >
      <div className="space-y-3">
        <p className="text-sm text-muted-foreground">
          Inbound emails where the AI matched a likely customer but wasn&apos;t
          confident enough to apply automatically. Accept to link the thread
          to the customer; reject to tell the matcher it was wrong.
        </p>

        {loading ? (
          <div className="text-sm text-muted-foreground">Loading…</div>
        ) : proposals.length === 0 ? (
          <div className="rounded border bg-muted/40 px-4 py-8 text-center text-sm text-muted-foreground">
            No pending matches — the matcher is handling everything on its own.
          </div>
        ) : (
          <div className="space-y-3">
            {proposals.map((p) => (
              <ProposalCard
                key={p.id}
                proposal={p}
                onResolved={(resolved) => {
                  if (resolved.status === "accepted") {
                    toast.success("Match applied");
                    // Offer a quick jump to the thread the match just touched.
                    const threadId =
                      (resolved.proposed_payload as { thread_id?: string })?.thread_id;
                    if (threadId) {
                      router.push(`/inbox?thread=${threadId}`);
                    }
                  } else if (resolved.status === "rejected") {
                    toast.info("Marked as not a match");
                  }
                  load();
                }}
                onError={(err) => toast.error(err.message || "Failed to resolve")}
              />
            ))}
          </div>
        )}
      </div>
    </PageLayout>
  );
}
