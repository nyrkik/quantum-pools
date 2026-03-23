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
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
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
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Plus, Trash2, Code2, Mail, CheckCircle2, Clock, Loader2, Users, Pencil, Check, X } from "lucide-react";

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

function formatPhone(value: string): string {
  const digits = value.replace(/\D/g, "").slice(0, 10);
  if (digits.length === 0) return "";
  if (digits.length <= 3) return `(${digits}`;
  if (digits.length <= 6) return `(${digits.slice(0, 3)}) ${digits.slice(3)}`;
  return `(${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6)}`;
}

function unformatPhone(value: string): string {
  return value.replace(/\D/g, "").slice(0, 10);
}

const ROLES = ["owner", "admin", "manager", "technician", "readonly"];

const ROLE_LABELS: Record<string, string> = {
  owner: "Owner",
  admin: "Admin",
  manager: "Manager",
  technician: "Technician",
  readonly: "Read Only",
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

function formatDate(iso: string | null) {
  if (!iso) return "Never";
  const d = new Date(iso);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDays = Math.floor(diffHr / 24);
  if (diffDays < 7) return `${diffDays}d ago`;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

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
  const [form, setForm] = useState({
    first_name: member.first_name,
    last_name: member.last_name,
    phone: member.phone || "",
    address: member.address || "",
    city: member.city || "",
    state: member.state || "",
    zip_code: member.zip_code || "",
    role: member.role,
  });

  const isDirty = editing && (
    form.first_name !== member.first_name ||
    form.last_name !== member.last_name ||
    form.phone !== (member.phone || "") ||
    form.address !== (member.address || "") ||
    form.city !== (member.city || "") ||
    form.state !== (member.state || "") ||
    form.zip_code !== (member.zip_code || "") ||
    form.role !== member.role
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
        role: form.role !== member.role ? form.role : undefined,
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
      role: member.role,
    });
    setEditing(false);
  };

  const handlePhoneChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setForm({ ...form, phone: formatPhone(e.target.value) });
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
          <p className="text-sm text-muted-foreground truncate">{member.email}</p>
          <div className="flex items-center gap-1.5 mt-1">
            <Badge variant={roleBadgeVariant(member.role)}>{ROLE_LABELS[member.role]}</Badge>
            {member.is_verified ? (
              <Badge variant="outline" className="border-green-400 text-green-600 text-[10px]">
                <CheckCircle2 className="h-2.5 w-2.5 mr-0.5" />Verified
              </Badge>
            ) : (
              <Badge variant="outline" className="border-amber-400 text-amber-600 text-[10px]">
                <Clock className="h-2.5 w-2.5 mr-0.5" />Pending
              </Badge>
            )}
            {!member.is_active && (
              <Badge variant="destructive" className="text-[10px]">Deactivated</Badge>
            )}
          </div>
        </div>
      </div>

      {/* Edit / Save bar */}
      <div className="flex items-center justify-between border-b pb-3">
        {!editing ? (
          <Button variant="outline" size="sm" onClick={() => setEditing(true)}>
            <Pencil className="h-3.5 w-3.5 mr-1.5" />Edit Profile
          </Button>
        ) : (
          <div className="flex gap-2">
            <Button size="sm" onClick={handleSave} disabled={saving || !isDirty}>
              {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" /> : <Check className="h-3.5 w-3.5 mr-1.5" />}
              Save
            </Button>
            <Button variant="ghost" size="sm" onClick={handleCancel}>Cancel</Button>
          </div>
        )}
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
          <p className="text-sm">{member.email}</p>
        </div>

        <div className="space-y-1">
          <Label className="text-xs text-muted-foreground">Phone</Label>
          {editing ? (
            <Input
              value={form.phone}
              onChange={handlePhoneChange}
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

      {/* Role & Access */}
      <div className="space-y-4">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Role & Access</p>
        <div className="space-y-1">
          <Label className="text-xs text-muted-foreground">Role</Label>
          {editing && member.role !== "owner" ? (
            <Select value={form.role} onValueChange={(v) => setForm({ ...form, role: v })}>
              <SelectTrigger className="h-8 text-sm w-40">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ROLES.filter(r => isOwner || r !== "owner").map(r => (
                  <SelectItem key={r} value={r} className="text-sm">{ROLE_LABELS[r]}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          ) : (
            <p className="text-sm font-medium">{ROLE_LABELS[member.role]}</p>
          )}
        </div>
      </div>

      {/* Account Info */}
      <div className="space-y-3">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Account</p>
        <div className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
          <div>
            <p className="text-xs text-muted-foreground">Status</p>
            <p className={!member.is_active ? "text-red-600 font-medium" : ""}>{member.is_active ? "Active" : "Deactivated"}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Verification</p>
            <p className={!member.is_verified ? "text-amber-600" : ""}>{member.is_verified ? "Verified" : "Pending setup"}</p>
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
        {!member.is_verified && (
          <Button
            variant="outline"
            size="sm"
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
            {resending ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" /> : <Mail className="h-3.5 w-3.5 mr-1.5" />}
            Resend Invite Email
          </Button>
        )}
      </div>
    </div>
  );
}

export default function TeamPage() {
  const { role: myRole } = useAuth();
  const isOwner = myRole === "owner";
  const [members, setMembers] = useState<TeamMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [resending, setResending] = useState<string | null>(null);
  const [selectedMember, setSelectedMember] = useState<TeamMember | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.get<TeamMember[]>("/v1/team");
      setMembers(data);
    } catch {
      toast.error("Failed to load team");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleInvite = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    try {
      await api.post("/v1/team/invite", {
        email: form.get("email"),
        first_name: form.get("first_name"),
        last_name: form.get("last_name"),
        role: form.get("role"),
        phone: form.get("phone") || undefined,
      });
      toast.success("Invite sent");
      setInviteOpen(false);
      load();
    } catch (err: unknown) {
      const msg = (err as { message?: string })?.message || "Failed to invite";
      toast.error(msg);
    }
  };

  const handleResendInvite = async (memberId: string) => {
    setResending(memberId);
    try {
      await api.post(`/v1/team/${memberId}/resend-invite`, {});
      toast.success("Invite resent");
    } catch (err: unknown) {
      const msg = (err as { message?: string })?.message || "Failed to resend";
      toast.error(msg);
    } finally {
      setResending(null);
    }
  };

  const handleRoleChange = async (memberId: string, role: string) => {
    try {
      await api.put(`/v1/team/${memberId}`, { role });
      toast.success("Role updated");
      load();
    } catch (err: unknown) {
      const msg = (err as { message?: string })?.message || "Failed to update role";
      toast.error(msg);
    }
  };

  const handleToggleDeveloper = async (memberId: string, isDeveloper: boolean) => {
    try {
      await api.put(`/v1/team/${memberId}/developer`, { is_developer: isDeveloper });
      toast.success(isDeveloper ? "Developer mode enabled" : "Developer mode disabled");
      load();
    } catch (err: unknown) {
      const msg = (err as { message?: string })?.message || "Failed to toggle developer";
      toast.error(msg);
    }
  };

  const handleToggleActive = async (memberId: string, isActive: boolean) => {
    try {
      await api.put(`/v1/team/${memberId}`, { is_active: isActive });
      toast.success(isActive ? "Member activated" : "Member deactivated");
      load();
    } catch (err: unknown) {
      const msg = (err as { message?: string })?.message || "Failed to update";
      toast.error(msg);
    }
  };

  const handleRemove = async (memberId: string) => {
    try {
      await api.delete(`/v1/team/${memberId}`);
      toast.success("Member removed");
      load();
    } catch (err: unknown) {
      const msg = (err as { message?: string })?.message || "Failed to remove";
      toast.error(msg);
    }
  };

  const verified = members.filter(m => m.is_verified).length;
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
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Invite Team Member</DialogTitle>
            </DialogHeader>
            <form onSubmit={handleInvite} className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-2">
                  <Label htmlFor="first_name">First Name</Label>
                  <Input id="first_name" name="first_name" required />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="last_name">Last Name</Label>
                  <Input id="last_name" name="last_name" required />
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <Input id="email" name="email" type="email" required />
                <p className="text-xs text-muted-foreground">They'll receive an email to set up their password</p>
              </div>
              <div className="space-y-2">
                <Label htmlFor="phone">Phone (optional)</Label>
                <Input id="phone" name="phone" type="tel" />
              </div>
              <div className="space-y-2">
                <Label>Role</Label>
                <Select name="role" defaultValue="technician">
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {ROLES.filter(r => isOwner || r !== "owner").map(r => (
                      <SelectItem key={r} value={r}>{ROLE_LABELS[r]}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <Button type="submit" className="w-full">Send Invite</Button>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow className="bg-slate-100 dark:bg-slate-800">
              <TableHead className="text-xs font-medium uppercase tracking-wide">Name</TableHead>
              <TableHead className="text-xs font-medium uppercase tracking-wide hidden sm:table-cell">Email</TableHead>
              <TableHead className="text-xs font-medium uppercase tracking-wide">Role</TableHead>
              <TableHead className="text-xs font-medium uppercase tracking-wide text-center">Status</TableHead>
              <TableHead className="text-xs font-medium uppercase tracking-wide hidden md:table-cell">Last Login</TableHead>
              {isOwner && <TableHead className="text-xs font-medium uppercase tracking-wide text-center">Dev</TableHead>}
              <TableHead className="text-xs font-medium uppercase tracking-wide text-center">Active</TableHead>
              <TableHead className="w-10"></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow>
                <TableCell colSpan={isOwner ? 8 : 7} className="text-center py-8">
                  <Loader2 className="h-5 w-5 animate-spin mx-auto text-muted-foreground" />
                </TableCell>
              </TableRow>
            ) : members.length === 0 ? (
              <TableRow>
                <TableCell colSpan={isOwner ? 8 : 7} className="text-center py-8 text-muted-foreground">No team members</TableCell>
              </TableRow>
            ) : (
              members.map((m, i) => (
                <TableRow key={m.id} className={`cursor-pointer hover:bg-blue-50 dark:hover:bg-blue-950 ${i % 2 === 1 ? "bg-slate-50 dark:bg-slate-900" : ""}`} onClick={() => setSelectedMember(m)}>
                  <TableCell>
                    <div>
                      <span className="font-medium">{m.first_name} {m.last_name}</span>
                      {m.is_developer && (
                        <Badge variant="outline" className="ml-2 text-amber-600 border-amber-300 text-[10px] px-1 py-0">
                          <Code2 className="h-2.5 w-2.5 mr-0.5" />DEV
                        </Badge>
                      )}
                    </div>
                    <p className="text-xs text-muted-foreground sm:hidden">{m.email}</p>
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground hidden sm:table-cell">{m.email}</TableCell>
                  <TableCell>
                    {m.role === "owner" ? (
                      <Badge variant={roleBadgeVariant(m.role)}>{ROLE_LABELS[m.role]}</Badge>
                    ) : (
                      <Select
                        value={m.role}
                        onValueChange={(v) => handleRoleChange(m.id, v)}
                      >
                        <SelectTrigger className="h-7 w-28 text-xs">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {ROLES.filter(r => isOwner || r !== "owner").map(r => (
                            <SelectItem key={r} value={r} className="text-xs">{ROLE_LABELS[r]}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    )}
                  </TableCell>
                  <TableCell className="text-center">
                    {m.is_verified ? (
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
                  {isOwner && (
                    <TableCell className="text-center">
                      <Switch
                        checked={m.is_developer}
                        onCheckedChange={(v) => handleToggleDeveloper(m.id, v)}
                        className="scale-75"
                      />
                    </TableCell>
                  )}
                  <TableCell className="text-center">
                    {m.role === "owner" ? (
                      <Badge variant="default" className="text-[10px]">Always</Badge>
                    ) : (
                      <Switch
                        checked={m.is_active}
                        onCheckedChange={(v) => handleToggleActive(m.id, v)}
                        className="scale-75"
                      />
                    )}
                  </TableCell>
                  <TableCell>
                    {m.role !== "owner" && (
                      <AlertDialog>
                        <AlertDialogTrigger asChild>
                          <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground hover:text-destructive">
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        </AlertDialogTrigger>
                        <AlertDialogContent>
                          <AlertDialogHeader>
                            <AlertDialogTitle>Remove {m.first_name} {m.last_name}?</AlertDialogTitle>
                            <AlertDialogDescription>
                              This will remove them from the organization. This action cannot be undone.
                            </AlertDialogDescription>
                          </AlertDialogHeader>
                          <AlertDialogFooter>
                            <AlertDialogCancel>Cancel</AlertDialogCancel>
                            <AlertDialogAction onClick={() => handleRemove(m.id)}>Remove</AlertDialogAction>
                          </AlertDialogFooter>
                        </AlertDialogContent>
                      </AlertDialog>
                    )}
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      {/* Member detail sheet */}
      <Sheet open={!!selectedMember} onOpenChange={(open) => { if (!open) setSelectedMember(null); }}>
        <SheetContent className="w-full sm:max-w-md overflow-y-auto px-4 sm:px-6">
          <SheetHeader className="px-0">
            <SheetTitle>{selectedMember ? `${selectedMember.first_name} ${selectedMember.last_name}` : "Member"}</SheetTitle>
          </SheetHeader>
          {selectedMember && (
            <MemberDetail
              member={selectedMember}
              isOwner={isOwner}
              onUpdate={() => { load(); }}
              onClose={() => setSelectedMember(null)}
            />
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
}
