"use client";

import { useState, useEffect, useCallback } from "react";
import { useAuth } from "@/lib/auth-context";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";
import { Loader2, Save, Eye, EyeOff, ArrowLeft } from "lucide-react";
import Link from "next/link";
import { formatPhone, unformatPhone } from "@/lib/format";

const US_STATES = [
  "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA",
  "KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ",
  "NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT",
  "VA","WA","WV","WI","WY",
];

interface UserProfile {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  phone: string | null;
  address: string | null;
  city: string | null;
  state: string | null;
  zip_code: string | null;
}

const ROLE_LABELS: Record<string, string> = {
  owner: "Full Access",
  admin: "Admin",
  manager: "Standard",
  technician: "Limited",
  readonly: "View Only",
  custom: "Custom",
};

export default function ProfilePage() {
  const { user, role, organizationName, refreshUser } = useAuth();
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [form, setForm] = useState({
    first_name: "",
    last_name: "",
    phone: "",
    address: "",
    city: "",
    state: "",
    zip_code: "",
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  // Password change
  const [pwForm, setPwForm] = useState({ current: "", new_pw: "", confirm: "" });
  const [pwSaving, setPwSaving] = useState(false);
  const [showCurrent, setShowCurrent] = useState(false);
  const [showNew, setShowNew] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await api.get<{ user: UserProfile }>("/v1/auth/me");
      setProfile(data.user);
      setForm({
        first_name: data.user.first_name,
        last_name: data.user.last_name,
        phone: data.user.phone ? formatPhone(data.user.phone) : "",
        address: data.user.address || "",
        city: data.user.city || "",
        state: data.user.state || "",
        zip_code: data.user.zip_code || "",
      });
    } catch {
      toast.error("Failed to load profile");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const isDirty = profile && (
    form.first_name !== profile.first_name ||
    form.last_name !== profile.last_name ||
    unformatPhone(form.phone) !== (profile.phone || "") ||
    form.address !== (profile.address || "") ||
    form.city !== (profile.city || "") ||
    form.state !== (profile.state || "") ||
    form.zip_code !== (profile.zip_code || "")
  );

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.put("/v1/auth/profile", {
        first_name: form.first_name,
        last_name: form.last_name,
        phone: unformatPhone(form.phone) || null,
        address: form.address || null,
        city: form.city || null,
        state: form.state || null,
        zip_code: form.zip_code || null,
      });
      toast.success("Profile updated");
      refreshUser();
      load();
    } catch {
      toast.error("Failed to save");
    } finally {
      setSaving(false);
    }
  };

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    if (pwForm.new_pw !== pwForm.confirm) {
      toast.error("Passwords don't match");
      return;
    }
    if (pwForm.new_pw.length < 8) {
      toast.error("Password must be at least 8 characters");
      return;
    }
    setPwSaving(true);
    try {
      await api.post("/v1/auth/change-password", {
        current_password: pwForm.current,
        new_password: pwForm.new_pw,
      });
      toast.success("Password changed");
      setPwForm({ current: "", new_pw: "", confirm: "" });
    } catch (err: unknown) {
      const msg = (err as { detail?: string })?.detail || (err as { message?: string })?.message || "Failed to change password";
      toast.error(msg);
    } finally {
      setPwSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-2xl">
      <div className="flex items-center gap-3">
        <Link href="/dashboard">
          <Button variant="ghost" size="icon" className="h-8 w-8">
            <ArrowLeft className="h-4 w-4" />
          </Button>
        </Link>
        <div>
          <h1 className="text-2xl font-bold">My Profile</h1>
          <p className="text-sm text-muted-foreground">{ROLE_LABELS[role] || role} at {organizationName}</p>
        </div>
      </div>

      {/* Personal Info */}
      <Card className="shadow-sm">
        <CardHeader>
          <CardTitle className="text-base">Personal Information</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">First Name</Label>
              <Input
                value={form.first_name}
                onChange={(e) => setForm({ ...form, first_name: e.target.value })}
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Last Name</Label>
              <Input
                value={form.last_name}
                onChange={(e) => setForm({ ...form, last_name: e.target.value })}
              />
            </div>
          </div>

          <div className="space-y-1">
            <Label className="text-xs text-muted-foreground">Email</Label>
            <Input value={profile?.email || ""} disabled className="bg-muted" />
          </div>

          <div className="space-y-1">
            <Label className="text-xs text-muted-foreground">Phone</Label>
            <Input
              value={form.phone}
              onChange={(e) => setForm({ ...form, phone: formatPhone(e.target.value) })}
              placeholder="(916) 555-1234"
              type="tel"
            />
          </div>
        </CardContent>
      </Card>

      {/* Address */}
      <Card className="shadow-sm">
        <CardHeader>
          <CardTitle className="text-base">Address</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-1">
            <Label className="text-xs text-muted-foreground">Street</Label>
            <Input
              value={form.address}
              onChange={(e) => setForm({ ...form, address: e.target.value })}
              placeholder="123 Main St"
            />
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
            <div className="col-span-2 space-y-1">
              <Label className="text-xs text-muted-foreground">City</Label>
              <Input
                value={form.city}
                onChange={(e) => setForm({ ...form, city: e.target.value })}
                placeholder="Elk Grove"
              />
            </div>
            <div className="col-span-1 space-y-1">
              <Label className="text-xs text-muted-foreground">State</Label>
              <Select value={form.state} onValueChange={(v) => setForm({ ...form, state: v })}>
                <SelectTrigger>
                  <SelectValue placeholder="—" />
                </SelectTrigger>
                <SelectContent>
                  {US_STATES.map((s) => (
                    <SelectItem key={s} value={s}>{s}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="col-span-2 space-y-1">
              <Label className="text-xs text-muted-foreground">Zip</Label>
              <Input
                value={form.zip_code}
                onChange={(e) => setForm({ ...form, zip_code: e.target.value.replace(/\D/g, "").slice(0, 5) })}
                placeholder="95624"
                inputMode="numeric"
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Save profile */}
      {isDirty && (
        <Button onClick={handleSave} disabled={saving}>
          {saving ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Save className="h-4 w-4 mr-2" />}
          Save Changes
        </Button>
      )}

      {/* Change Password */}
      <Card className="shadow-sm">
        <CardHeader>
          <CardTitle className="text-base">Change Password</CardTitle>
          <CardDescription>Update your login password.</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleChangePassword} className="space-y-4 max-w-sm">
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Current Password</Label>
              <div className="relative">
                <Input
                  type={showCurrent ? "text" : "password"}
                  value={pwForm.current}
                  onChange={(e) => setPwForm({ ...pwForm, current: e.target.value })}
                  required
                />
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="absolute right-0 top-0 h-full w-10 text-muted-foreground"
                  onClick={() => setShowCurrent(!showCurrent)}
                >
                  {showCurrent ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </Button>
              </div>
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">New Password</Label>
              <div className="relative">
                <Input
                  type={showNew ? "text" : "password"}
                  value={pwForm.new_pw}
                  onChange={(e) => setPwForm({ ...pwForm, new_pw: e.target.value })}
                  required
                  minLength={8}
                />
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="absolute right-0 top-0 h-full w-10 text-muted-foreground"
                  onClick={() => setShowNew(!showNew)}
                >
                  {showNew ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </Button>
              </div>
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Confirm New Password</Label>
              <Input
                type="password"
                value={pwForm.confirm}
                onChange={(e) => setPwForm({ ...pwForm, confirm: e.target.value })}
                required
                minLength={8}
              />
              {pwForm.new_pw && pwForm.confirm && pwForm.new_pw !== pwForm.confirm && (
                <p className="text-xs text-red-600">Passwords don't match</p>
              )}
            </div>
            <Button
              type="submit"
              variant="outline"
              disabled={pwSaving || !pwForm.current || !pwForm.new_pw || !pwForm.confirm}
            >
              {pwSaving ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
              Change Password
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
