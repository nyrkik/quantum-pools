"use client";

import { use } from "react";
import { useRouter } from "next/navigation";
import { BackButton } from "@/components/ui/back-button";
import { ThreadDetailSheet } from "@/components/inbox/thread-detail-sheet";

export default function ThreadDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();

  return (
    <div>
      <div className="flex items-center gap-3 mb-4">
        <BackButton fallback="/inbox" label="" />
        <h1 className="text-lg font-semibold">Conversation</h1>
      </div>
      <ThreadDetailSheet
        threadId={id}
        onClose={() => router.push("/inbox")}
        onAction={() => {}}
      />
    </div>
  );
}
