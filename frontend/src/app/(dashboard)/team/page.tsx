"use client";

import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { toast } from "sonner";
import { Overlay, OverlayContent, OverlayHeader, OverlayTitle, OverlayBody } from "@/components/ui/overlay";
import { Plus, Trash2, Code2, Mail, CheckCircle2, Clock, Loader2, Users, Pencil, Check } from "lucide-react";
import { formatPhone, unformatPhone, formatRelativeDate } from "@/lib/format";

interface TeamMember {
  id: string;
  user_id: string;
  email: string;
  first_name: string;
  last_name: string;
  phone: string | null;
  address: string | null;
  city: string | null;
  state: string | null;
  zip_code: string | null;
  role: string;
  job_title: string | null;
  is_developer: boolean;
  is_active: boolean;
  is_verified: boolean;
  last_login: string | null;
  created_at: string;
}

const US_STATES = [
  "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA",
  "KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ",
  "NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT",
  "VA","WA","WV","WI","WY",
];

const ROLES = ["owner", "admin", "manager", "technician", "readonly"];

const ROLE_LABELS: Record<string, string> = {
  owner: "Full Access",
  admin: "Admin",
  manager: "Standard",
  technician: "Limited",
  readonly: "View Only",
  custom: "Custom",
};

const ROLE_DESCRIPTIONS: Record<string, string> = {
  owner: "Full access to all features and settings",
  admin: "Manage customers, billing, team. No org settings.",
  manager: "Manage daily operations. No billing or team access.",
  technician: "Own routes, visits, and readings only.",
  readonly: "View-only access across the platform.",
  custom: "Custom permission set assigned by admin.",
};

const roleBadgeVariant = (role: string) => {
  switch (role) {
    case "owner": return "default" as const;
    case "admin": return "default" as const;
    case "manager": return "secondary" as const;
    case "technician": return "outline" as const;
    default: return "outline" as const;
  }
};

const formatDate = formatRelativeDate;

function MemberDetail({
  member,
  isOwner,
  onUpdate,
  onClose,
}: {
  member: TeamMember;
  isOwner: boolean;
  onUpdate: () => void;
  onClose: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [resending, setResending] = useState(false);
  const [savingRole, setSavingRole] = useState(false);
  const [togglingDev, setTogglingDev] = useState(false);
  const [togglingActive, setTogglingActive] = useState(false);
  const isFullAccess = isOwner || member.role === "admin"; // who can manage

  const [form, setForm] = useState({
    first_name: member.first_name,
    last_name: member.last_name,
    phone: member.phone || "",
    address: member.address || "",
    city: member.city || "",
    state: member.state || "",
    zip_code: member.zip_code || "",
  });

  // Reset form when member changes (e.g., after save + reload)
  useEffect(() => {
    setForm({
      first_name: member.first_name,
      last_name: member.last_name,
      phone: member.phone || "",
      address: member.address || "",
      city: member.city || "",
      state: member.state || "",
      zip_code: member.zip_code || "",
    });
    setEditing(false);
  }, [member]);

  const isDirty = editing && (
    form.first_name !== member.first_name ||
    form.last_name !== member.last_name ||
    form.phone !== (member.phone || "") ||
    form.address !== (member.address || "") ||
    form.city !== (member.city || "") ||
    form.state !== (member.state || "") ||
    form.zip_code !== (member.zip_code || "")
  );

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.put(`/v1/team/${member.id}`, {
        first_name: form.first_name,
        last_name: form.last_name,
        phone: form.phone ? unformatPhone(form.phone) : null,
        address: form.address || null,
        city: form.city || null,
        state: form.state || null,
        zip_code: form.zip_code || null,
      });
      toast.success("Profile updated");
      setEditing(false);
      onUpdate();
    } catch (err: unknown) {
      toast.error((err as { message?: string })?.message || "Failed to update");
    } finally {
      setSaving(false);
    }
  };

  const handleCancel = () => {
    setForm({
      first_name: member.first_name,
      last_name: member.last_name,
      phone: member.phone || "",
      address: member.address || "",
      city: member.city || "",
      state: member.state || "",
      zip_code: member.zip_code || "",
    });
    setEditing(false);
  };

  const handleToggleDev = async (checked: boolean) => {
    setTogglingDev(true);
    try {
      await api.put(`/v1/team/${member.id}/developer`, { is_developer: checked });
      toast.success(checked ? "Developer mode enabled" : "Developer mode disabled");
      onUpdate();
    } catch {
      toast.error("Failed to toggle developer mode");
    } finally {
      setTogglingDev(false);
    }
  };

  const handleToggleActive = async (checked: boolean) => {
    setTogglingActive(true);
    try {
      await api.put(`/v1/team/${member.id}`, { is_active: checked });
      toast.success(checked ? "Member activated" : "Member deactivated");
      onUpdate();
    } catch {
      toast.error("Failed to update status");
    } finally {
      setTogglingActive(false);
    }
  };

  const handleRemove = async () => {
    try {
      await api.delete(`/v1/team/${member.id}`);
      toast.success("Member removed");
      onClose();
      onUpdate();
    } catch {
      toast.error("Failed to remove member");
    }
  };

  const displayPhone = member.phone ? formatPhone(member.phone) : null;
  const displayAddress = [member.address, member.city, member.state, member.zip_code]
    .filter(Boolean).join(", ") || null;

  return (
    <div className="space-y-6 pt-2">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="flex h-14 w-14 flex-shrink-0 items-center justify-center rounded-full bg-primary text-xl font-semibold text-primary-foreground">
          {member.first_name[0]}{member.last_name[0]}
        </div>
        <div className="flex-1 min-w-0">
          <p className="font-semibold text-lg">{member.first_name} {member.last_name}</p>
          {member.job_title && (
            <p className="text-sm text-muted-foreground">{member.job_title}</p>
          )}
          <div className="flex items-center gap-1.5 mt-1">
            <Badge variant={roleBadgeVariant(member.role)}>{ROLE_LABELS[member.role]}</Badge>
            {!member.is_active && (
              <Badge variant="destructive" className="text-[10px]">Deactivated</Badge>
            )}
            {member.is_developer && (
              <Badge variant="outline" className="text-amber-600 border-amber-300 text-[10px] px-1 py-0">
                <Code2 className="h-2.5 w-2.5 mr-0.5" />DEV
              </Badge>
            )}
          </div>
        </div>
        {!editing && (
          <Button variant="outline" size="sm" onClick={() => setEditing(true)}>
            <Pencil className="h-3.5 w-3.5 mr-1.5" />Edit
          </Button>
        )}
      </div>

      {/* Permission Level — always interactive, no edit mode needed */}
      <div className="space-y-3 rounded-lg border bg-muted/30 p-4">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Permission Level</p>
        <div className="flex flex-wrap gap-2">
          {ROLES.map(r => (
            <button
              key={r}
              type="button"
              disabled={savingRole || r === member.role}
              onClick={async () => {
                if (r === member.role) return;
                setSavingRole(true);
                try {
                  await api.put(`/v1/team/${member.id}`, { role: r });
                  toast.success(`Permission updated to ${ROLE_LABELS[r]}`);
                  onUpdate();
                } catch (err: unknown) {
                  toast.error((err as { message?: string })?.message || "Failed to update permission");
                } finally {
                  setSavingRole(false);
                }
              }}
              className={`px-3 py-1.5 text-sm rounded-md border transition-colors ${
                member.role === r
                  ? "bg-primary text-primary-foreground border-primary"
                  : "bg-background text-muted-foreground border-input hover:bg-accent hover:text-foreground"
              }`}
            >
              {ROLE_LABELS[r]}
            </button>
          ))}
        </div>
        <p className="text-xs text-muted-foreground">
          {ROLE_DESCRIPTIONS[member.role] || ""}
        </p>
      </div>

      {/* Personal Info */}
      <div className="space-y-4">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Personal Information</p>

        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1">
            <Label className="text-xs text-muted-foreground">First Name</Label>
            {editing ? (
              <Input value={form.first_name} onChange={(e) => setForm({ ...form, first_name: e.target.value })} className="h-8 text-sm" />
            ) : (
              <p className="text-sm font-medium">{member.first_name}</p>
            )}
          </div>
          <div className="space-y-1">
            <Label className="text-xs text-muted-foreground">Last Name</Label>
            {editing ? (
              <Input value={form.last_name} onChange={(e) => setForm({ ...form, last_name: e.target.value })} className="h-8 text-sm" />
            ) : (
              <p className="text-sm font-medium">{member.last_name}</p>
            )}
          </div>
        </div>

        <div className="space-y-1">
          <Label className="text-xs text-muted-foreground">Email</Label>
          <div className="flex items-center gap-2">
            <p className="text-sm">{member.email}</p>
            {member.is_verified ? (
              <Badge variant="outline" className="border-green-400 text-green-600 text-[10px]">
                <CheckCircle2 className="h-2.5 w-2.5 mr-0.5" />Verified
              </Badge>
            ) : (
              <div className="flex items-center gap-1.5">
                <Badge variant="outline" className="border-amber-400 text-amber-600 text-[10px]">
                  <Clock className="h-2.5 w-2.5 mr-0.5" />Pending
                </Badge>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-6 text-xs text-muted-foreground hover:text-primary"
                  disabled={resending}
                  onClick={async () => {
                    setResending(true);
                    try {
                      await api.post(`/v1/team/${member.id}/resend-invite`, {});
                      toast.success("Invite email resent");
                    } catch {
                      toast.error("Failed to resend invite");
                    } finally {
                      setResending(false);
                    }
                  }}
                >
                  {resending ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : <Mail className="h-3 w-3 mr-1" />}
                  Resend
                </Button>
              </div>
            )}
          </div>
        </div>

        <div className="space-y-1">
          <Label className="text-xs text-muted-foreground">Phone</Label>
          {editing ? (
            <Input
              value={form.phone}
              onChange={(e) => setForm({ ...form, phone: formatPhone(e.target.value) })}
              className="h-8 text-sm"
              placeholder="(916) 555-1234"
              type="tel"
            />
          ) : (
            <p className="text-sm">{displayPhone || <span className="text-muted-foreground">—</span>}</p>
          )}
        </div>
      </div>

      {/* Address */}
      <div className="space-y-4">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Address</p>
        {editing ? (
          <>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Street</Label>
              <Input value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} className="h-8 text-sm" placeholder="123 Main St" />
            </div>
            <div className="grid grid-cols-5 gap-2">
              <div className="col-span-2 space-y-1">
                <Label className="text-xs text-muted-foreground">City</Label>
                <Input value={form.city} onChange={(e) => setForm({ ...form, city: e.target.value })} className="h-8 text-sm" placeholder="Elk Grove" />
              </div>
              <div className="col-span-1 space-y-1">
                <Label className="text-xs text-muted-foreground">State</Label>
                <Select value={form.state} onValueChange={(v) => setForm({ ...form, state: v })}>
                  <SelectTrigger className="h-8 text-sm">
                    <SelectValue placeholder="—" />
                  </SelectTrigger>
                  <SelectContent>
                    {US_STATES.map((s) => (
                      <SelectItem key={s} value={s} className="text-sm">{s}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="col-span-2 space-y-1">
                <Label className="text-xs text-muted-foreground">Zip</Label>
                <Input value={form.zip_code} onChange={(e) => setForm({ ...form, zip_code: e.target.value.replace(/\D/g, "").slice(0, 5) })} className="h-8 text-sm" placeholder="95624" inputMode="numeric" />
              </div>
            </div>
          </>
        ) : (
          <p className="text-sm">{displayAddress || <span className="text-muted-foreground">—</span>}</p>
        )}
      </div>

      {/* Account Settings */}
      <div className="space-y-4">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Account</p>
        <div className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
          <div>
            <p className="text-xs text-muted-foreground">Status</p>
            <p className={!member.is_active ? "text-red-600 font-medium" : ""}>{member.is_active ? "Active" : "Deactivated"}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Last Login</p>
            <p>{member.last_login ? formatDate(member.last_login) : "Never"}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Member Since</p>
            <p>{new Date(member.created_at).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}</p>
          </div>
        </div>

        <div className="space-y-3 pt-2 border-t">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium">Active</p>
              <p className="text-xs text-muted-foreground">Deactivated members cannot log in</p>
            </div>
            <Switch
              checked={member.is_active}
              onCheckedChange={handleToggleActive}
              disabled={togglingActive}
            />
          </div>
          {(isOwner || member.role === "admin") && (
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium">Developer Mode</p>
                <p className="text-xs text-muted-foreground">Access dev tools and org switching</p>
              </div>
              <Switch
                checked={member.is_developer}
                onCheckedChange={handleToggleDev}
                disabled={togglingDev}
              />
            </div>
          )}
        </div>
      </div>

      {/* Save / Cancel — only visible when dirty */}
      {isDirty && (
        <div className="flex gap-2 pt-2 border-t sticky bottom-0 bg-background pb-2">
          <Button className="flex-1" onClick={handleSave} disabled={saving}>
            {saving ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Check className="h-4 w-4 mr-2" />}
            Save Changes
          </Button>
          <Button variant="ghost" onClick={handleCancel}>Cancel</Button>
        </div>
      )}

      {/* Remove member — bottom, behind confirmation */}
      {!editing && (
        <div className="pt-2 border-t">
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button variant="ghost" size="sm" className="w-full text-muted-foreground hover:text-destructive">
                <Trash2 className="h-3.5 w-3.5 mr-2" />
                Remove from organization
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Remove {member.first_name} {member.last_name}?</AlertDialogTitle>
                <AlertDialogDescription>
                  This will remove them from the organization. This action cannot be undone.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction onClick={handleRemove}>Remove</AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>
      )}
    </div>
  );
}

export default function TeamPage() {
  const { role: myRole } = useAuth();
  const isOwner = myRole === "owner";
  const [members, setMembers] = useState<TeamMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [inviteDraft, setInviteDraft] = useState({ first_name: "", last_name: "", email: "", phone: "", role: "technician" });
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

  const handleInvite = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    try {
      await api.post("/v1/team/invite", {
        email: inviteDraft.email,
        first_name: inviteDraft.first_name,
        last_name: inviteDraft.last_name,
        role: inviteDraft.role,
        phone: inviteDraft.phone || undefined,
      });
      toast.success("Invite sent");
      setInviteDraft({ first_name: "", last_name: "", email: "", phone: "", role: "technician" });
      setInviteOpen(false);
      load();
    } catch (err: unknown) {
      const msg = (err as { message?: string })?.message || "Failed to invite";
      toast.error(msg);
    }
  };

  const pending = members.filter(m => !m.is_verified).length;

  return (
    <div className="space-y-4 sm:space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <Users className="h-6 w-6 text-primary" />
          <div>
            <h1 className="text-2xl font-bold">Team</h1>
            <p className="text-muted-foreground text-sm">
              {members.length} member{members.length !== 1 ? "s" : ""}
              {pending > 0 && <span className="text-amber-600 ml-1">({pending} pending)</span>}
            </p>
          </div>
        </div>
        <Dialog open={inviteOpen} onOpenChange={setInviteOpen}>
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
                  <Input id="first_name" value={inviteDraft.first_name} onChange={(e) => setInviteDraft({ ...inviteDraft, first_name: e.target.value })} required />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="last_name">Last Name</Label>
                  <Input id="last_name" value={inviteDraft.last_name} onChange={(e) => setInviteDraft({ ...inviteDraft, last_name: e.target.value })} required />
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <Input id="email" type="email" value={inviteDraft.email} onChange={(e) => setInviteDraft({ ...inviteDraft, email: e.target.value })} required />
                <p className="text-xs text-muted-foreground">They'll receive an email to set up their password</p>
              </div>
              <div className="space-y-2">
                <Label htmlFor="phone">Phone (optional)</Label>
                <Input id="phone" type="tel" value={inviteDraft.phone} onChange={(e) => setInviteDraft({ ...inviteDraft, phone: formatPhone(e.target.value) })} placeholder="(916) 555-1234" />
              </div>
              <div className="space-y-2">
                <Label>Permission Level</Label>
                <div className="flex flex-wrap gap-2">
                  {ROLES.filter(r => isOwner || r !== "owner").map(r => (
                    <button
                      key={r}
                      type="button"
                      onClick={() => setInviteDraft({ ...inviteDraft, role: r })}
                      className={`px-3 py-1.5 text-sm rounded-md border transition-colors ${
                        inviteDraft.role === r
                          ? "bg-primary text-primary-foreground border-primary"
                          : "bg-background text-muted-foreground border-input hover:bg-accent hover:text-foreground"
                      }`}
                    >
                      {ROLE_LABELS[r]}
                    </button>
                  ))}
                </div>
                <p className="text-xs text-muted-foreground">{ROLE_DESCRIPTIONS[inviteDraft.role]}</p>
              </div>
              <Button type="submit" className="w-full">Send Invite</Button>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      {/* Read-only table */}
      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow className="bg-slate-100 dark:bg-slate-800">
              <TableHead className="text-xs font-medium uppercase tracking-wide">Name</TableHead>
              <TableHead className="text-xs font-medium uppercase tracking-wide hidden sm:table-cell">Email</TableHead>
              <TableHead className="text-xs font-medium uppercase tracking-wide">Permission</TableHead>
              <TableHead className="text-xs font-medium uppercase tracking-wide text-center">Status</TableHead>
              <TableHead className="text-xs font-medium uppercase tracking-wide hidden md:table-cell">Last Login</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow>
                <TableCell colSpan={5} className="text-center py-8">
                  <Loader2 className="h-5 w-5 animate-spin mx-auto text-muted-foreground" />
                </TableCell>
              </TableRow>
            ) : members.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} className="text-center py-8 text-muted-foreground">No team members</TableCell>
              </TableRow>
            ) : (
              members.map((m, i) => (
                <TableRow
                  key={m.id}
                  className={`cursor-pointer hover:bg-blue-50 dark:hover:bg-blue-950 ${i % 2 === 1 ? "bg-slate-50 dark:bg-slate-900" : ""}`}
                  onClick={() => setSelectedMember(m)}
                >
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{m.first_name} {m.last_name}</span>
                      {m.is_developer && (
                        <Badge variant="outline" className="text-amber-600 border-amber-300 text-[10px] px-1 py-0">
                          <Code2 className="h-2.5 w-2.5 mr-0.5" />DEV
                        </Badge>
                      )}
                    </div>
                    {m.job_title && (
                      <p className="text-xs text-muted-foreground">{m.job_title}</p>
                    )}
                    <p className="text-xs text-muted-foreground sm:hidden">{m.email}</p>
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground hidden sm:table-cell">{m.email}</TableCell>
                  <TableCell>
                    <Badge variant={roleBadgeVariant(m.role)}>{ROLE_LABELS[m.role] || m.role}</Badge>
                  </TableCell>
                  <TableCell className="text-center">
                    {!m.is_active ? (
                      <Badge variant="destructive" className="text-[10px]">Inactive</Badge>
                    ) : m.is_verified ? (
                      <Badge variant="outline" className="border-green-400 text-green-600 text-[10px]">
                        <CheckCircle2 className="h-2.5 w-2.5 mr-0.5" />Verified
                      </Badge>
                    ) : (
                      <Badge variant="outline" className="border-amber-400 text-amber-600 text-[10px]">
                        <Clock className="h-2.5 w-2.5 mr-0.5" />Pending
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground hidden md:table-cell">
                    {formatDate(m.last_login)}
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

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
    </div>
  );
}
