"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
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
import { Trash2, Code2, Mail, CheckCircle2, Clock, Loader2, Pencil, Check } from "lucide-react";
import { formatPhone, unformatPhone, formatRelativeDate } from "@/lib/format";
import { TeamMember, US_STATES, ROLES, ROLE_LABELS, ROLE_DESCRIPTIONS, roleBadgeVariant } from "./types";

interface MemberDetailProps {
  member: TeamMember;
  isOwner: boolean;
  onUpdate: () => void;
  onClose: () => void;
}

export function MemberDetail({ member, isOwner, onUpdate, onClose }: MemberDetailProps) {
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [resending, setResending] = useState(false);
  const [savingRole, setSavingRole] = useState(false);
  const [togglingDev, setTogglingDev] = useState(false);
  const [togglingActive, setTogglingActive] = useState(false);

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

      {/* Permission Level */}
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
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
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
            <p>{member.last_login ? formatRelativeDate(member.last_login) : "Never"}</p>
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

      {/* Save / Cancel */}
      {isDirty && (
        <div className="flex gap-2 pt-2 border-t sticky bottom-0 bg-background pb-2">
          <Button className="flex-1" onClick={handleSave} disabled={saving}>
            {saving ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Check className="h-4 w-4 mr-2" />}
            Save Changes
          </Button>
          <Button variant="ghost" onClick={handleCancel}>Cancel</Button>
        </div>
      )}

      {/* Remove member */}
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
