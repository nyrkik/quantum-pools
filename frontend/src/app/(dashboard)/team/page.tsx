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
import { Plus, Trash2, Code2 } from "lucide-react";

interface TeamMember {
  id: string;
  user_id: string;
  email: string;
  first_name: string;
  last_name: string;
  role: string;
  is_developer: boolean;
  is_active: boolean;
  created_at: string;
}

const ROLES = ["owner", "admin", "manager", "technician", "readonly"];

const roleBadgeVariant = (role: string) => {
  switch (role) {
    case "owner": return "default" as const;
    case "admin": return "default" as const;
    case "manager": return "secondary" as const;
    case "technician": return "outline" as const;
    default: return "outline" as const;
  }
};

export default function TeamPage() {
  const { role: myRole } = useAuth();
  const isOwner = myRole === "owner";
  const [members, setMembers] = useState<TeamMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [inviteOpen, setInviteOpen] = useState(false);

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
        password: form.get("password"),
      });
      toast.success("Team member added");
      setInviteOpen(false);
      load();
    } catch (err: unknown) {
      const msg = (err as { message?: string })?.message || "Failed to invite";
      toast.error(msg);
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

  return (
    <div className="space-y-4 sm:space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight">Team</h1>
          <p className="text-muted-foreground text-sm">{members.length} members</p>
        </div>
        <Dialog open={inviteOpen} onOpenChange={setInviteOpen}>
          <DialogTrigger asChild>
            <Button>
              <Plus className="mr-2 h-4 w-4" />
              <span className="hidden sm:inline">Add Member</span>
              <span className="sm:hidden">Add</span>
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Add Team Member</DialogTitle>
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
              </div>
              <div className="space-y-2">
                <Label htmlFor="password">Password</Label>
                <Input id="password" name="password" type="password" required minLength={8} />
              </div>
              <div className="space-y-2">
                <Label>Role</Label>
                <Select name="role" defaultValue="technician">
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {ROLES.filter(r => isOwner || r !== "owner").map(r => (
                      <SelectItem key={r} value={r} className="capitalize">{r}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <Button type="submit" className="w-full">Add Member</Button>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead className="hidden sm:table-cell">Email</TableHead>
              <TableHead>Role</TableHead>
              {isOwner && <TableHead className="text-center">Dev</TableHead>}
              <TableHead className="text-center">Active</TableHead>
              <TableHead className="w-10"></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow>
                <TableCell colSpan={isOwner ? 6 : 5} className="text-center py-8">Loading...</TableCell>
              </TableRow>
            ) : members.length === 0 ? (
              <TableRow>
                <TableCell colSpan={isOwner ? 6 : 5} className="text-center py-8 text-muted-foreground">No team members</TableCell>
              </TableRow>
            ) : (
              members.map((m, i) => (
                <TableRow key={m.id} className={`hover:bg-blue-50 dark:hover:bg-blue-950 ${i % 2 === 1 ? "bg-slate-50 dark:bg-slate-900" : ""}`}>
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
                      <Badge variant={roleBadgeVariant(m.role)} className="capitalize">{m.role}</Badge>
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
                            <SelectItem key={r} value={r} className="text-xs capitalize">{r}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    )}
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
    </div>
  );
}
