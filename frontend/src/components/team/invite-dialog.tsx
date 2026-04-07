"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { toast } from "sonner";
import { Plus } from "lucide-react";
import { formatPhone } from "@/lib/format";
import { ROLES, ROLE_LABELS, ROLE_DESCRIPTIONS } from "./types";

interface InviteDialogProps {
  isOwner: boolean;
  onInvited: () => void;
}

export function InviteDialog({ isOwner, onInvited }: InviteDialogProps) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState({ first_name: "", last_name: "", email: "", phone: "", role: "technician" });

  const handleInvite = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    try {
      await api.post("/v1/team/invite", {
        email: draft.email,
        first_name: draft.first_name,
        last_name: draft.last_name,
        role: draft.role,
        phone: draft.phone || undefined,
      });
      toast.success("Invite sent");
      setDraft({ first_name: "", last_name: "", email: "", phone: "", role: "technician" });
      setOpen(false);
      onInvited();
    } catch (err: unknown) {
      const msg = (err as { message?: string })?.message || "Failed to invite";
      toast.error(msg);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>
          <Plus className="mr-2 h-4 w-4" />
          <span className="hidden sm:inline">Invite Member</span>
          <span className="sm:hidden">Invite</span>
        </Button>
      </DialogTrigger>
      <DialogContent onInteractOutside={(e) => e.preventDefault()} onEscapeKeyDown={(e) => e.preventDefault()} onPointerDownOutside={(e) => e.preventDefault()}>
        <DialogHeader>
          <DialogTitle>Invite Team Member</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleInvite} className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="first_name">First Name</Label>
              <Input id="first_name" value={draft.first_name} onChange={(e) => setDraft({ ...draft, first_name: e.target.value })} required />
            </div>
            <div className="space-y-2">
              <Label htmlFor="last_name">Last Name</Label>
              <Input id="last_name" value={draft.last_name} onChange={(e) => setDraft({ ...draft, last_name: e.target.value })} required />
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="email">Email</Label>
            <Input id="email" type="email" value={draft.email} onChange={(e) => setDraft({ ...draft, email: e.target.value })} required />
            <p className="text-xs text-muted-foreground">They'll receive an email to set up their password</p>
          </div>
          <div className="space-y-2">
            <Label htmlFor="phone">Phone (optional)</Label>
            <Input id="phone" type="tel" value={draft.phone} onChange={(e) => setDraft({ ...draft, phone: formatPhone(e.target.value) })} placeholder="(916) 555-1234" />
          </div>
          <div className="space-y-2">
            <Label>Permission Level</Label>
            <div className="flex flex-wrap gap-2">
              {ROLES.filter(r => isOwner || r !== "owner").map(r => (
                <button
                  key={r}
                  type="button"
                  onClick={() => setDraft({ ...draft, role: r })}
                  className={`px-3 py-1.5 text-sm rounded-md border transition-colors ${
                    draft.role === r
                      ? "bg-primary text-primary-foreground border-primary"
                      : "bg-background text-muted-foreground border-input hover:bg-accent hover:text-foreground"
                  }`}
                >
                  {ROLE_LABELS[r]}
                </button>
              ))}
            </div>
            <p className="text-xs text-muted-foreground">{ROLE_DESCRIPTIONS[draft.role]}</p>
          </div>
          <Button type="submit" className="w-full">Send Invite</Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
