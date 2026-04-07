"use client";

import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { toast } from "sonner";
import { Overlay, OverlayContent, OverlayHeader, OverlayTitle, OverlayBody } from "@/components/ui/overlay";
import { Users } from "lucide-react";
import { PageLayout } from "@/components/layout/page-layout";
import { TeamMember } from "@/components/team/types";
import { MemberDetail } from "@/components/team/member-detail";
import { InviteDialog } from "@/components/team/invite-dialog";
import { TeamTable } from "@/components/team/team-table";

export default function TeamPage() {
  const { role: myRole } = useAuth();
  const isOwner = myRole === "owner";
  const [members, setMembers] = useState<TeamMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedMember, setSelectedMember] = useState<TeamMember | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.get<TeamMember[]>("/v1/team");
      setMembers(data);
      // If a member is selected, refresh their data
      if (selectedMember) {
        const updated = data.find(m => m.id === selectedMember.id);
        if (updated) setSelectedMember(updated);
      }
    } catch {
      toast.error("Failed to load team");
    } finally {
      setLoading(false);
    }
  }, [selectedMember]);

  useEffect(() => { load(); }, []);

  const pending = members.filter(m => !m.is_verified).length;

  return (
    <PageLayout
      title="Team"
      icon={<Users className="h-5 w-5 text-muted-foreground" />}
      subtitle={
        <>
          {members.length} member{members.length !== 1 ? "s" : ""}
          {pending > 0 && <span className="text-amber-600 ml-1">({pending} pending)</span>}
        </>
      }
      action={<InviteDialog isOwner={isOwner} onInvited={load} />}
    >
      <TeamTable members={members} loading={loading} onSelectMember={setSelectedMember} />

      {/* Member detail overlay */}
      <Overlay open={!!selectedMember} onOpenChange={(open) => { if (!open) setSelectedMember(null); }}>
        <OverlayContent>
          <OverlayHeader>
            <OverlayTitle>{selectedMember ? `${selectedMember.first_name} ${selectedMember.last_name}` : "Member"}</OverlayTitle>
          </OverlayHeader>
          <OverlayBody>
            {selectedMember && (
              <MemberDetail
                member={selectedMember}
                isOwner={isOwner}
                onUpdate={() => { load(); }}
                onClose={() => setSelectedMember(null)}
              />
            )}
          </OverlayBody>
        </OverlayContent>
      </Overlay>
    </PageLayout>
  );
}
