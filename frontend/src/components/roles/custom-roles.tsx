"use client";

import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Plus, Pencil, Trash2, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { PermissionEditor, type PermissionCatalog } from "./permission-editor";

interface OrgRolePermission {
  slug: string;
  scope: string;
}

interface OrgRole {
  id: string;
  slug: string;
  name: string;
  description: string | null;
  based_on_preset_id: string | null;
  is_active: boolean;
  permissions: OrgRolePermission[];
  created_at: string;
  updated_at: string;
}

interface Preset {
  slug: string;
  name: string;
  permissions: { slug: string; scope: string }[];
}

const PRESET_LABELS: Record<string, string> = {
  owner: "Full Access",
  admin: "Admin",
  manager: "Standard",
  technician: "Limited",
  readonly: "View Only",
};

interface CustomRolesProps {
  catalog: PermissionCatalog | null;
}

export function CustomRoles({ catalog }: CustomRolesProps) {
  const [roles, setRoles] = useState<OrgRole[]>([]);
  const [presets, setPresets] = useState<Preset[]>([]);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingRole, setEditingRole] = useState<OrgRole | null>(null);
  const [saving, setSaving] = useState(false);

  // Form state
  const [formName, setFormName] = useState("");
  const [formSlug, setFormSlug] = useState("");
  const [formDescription, setFormDescription] = useState("");
  const [formBasedOn, setFormBasedOn] = useState<string>("");
  const [formPermissions, setFormPermissions] = useState<Set<string>>(new Set());

  const fetchRoles = useCallback(async () => {
    try {
      const [rolesData, presetsData] = await Promise.all([
        api.get<OrgRole[]>("/v1/permissions/roles"),
        api.get<Preset[]>("/v1/permissions/presets"),
      ]);
      setRoles(rolesData);
      setPresets(presetsData);
    } catch {
      toast.error("Failed to load roles");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchRoles();
  }, [fetchRoles]);

  const openCreate = () => {
    setEditingRole(null);
    setFormName("");
    setFormSlug("");
    setFormDescription("");
    setFormBasedOn("");
    setFormPermissions(new Set());
    setDialogOpen(true);
  };

  const openEdit = (role: OrgRole) => {
    setEditingRole(role);
    setFormName(role.name);
    setFormSlug(role.slug);
    setFormDescription(role.description || "");
    setFormBasedOn("");
    setFormPermissions(new Set(role.permissions.map((p) => p.slug)));
    setDialogOpen(true);
  };

  const handleBasedOnChange = (presetSlug: string) => {
    setFormBasedOn(presetSlug);
    const preset = presets.find((p) => p.slug === presetSlug);
    if (preset) {
      setFormPermissions(new Set(preset.permissions.map((p) => p.slug)));
    }
  };

  const handleNameChange = (name: string) => {
    setFormName(name);
    if (!editingRole) {
      setFormSlug(name.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, ""));
    }
  };

  const handleSave = async () => {
    if (!formName.trim() || !formSlug.trim()) {
      toast.error("Name and slug are required");
      return;
    }
    setSaving(true);
    try {
      const permissions = Array.from(formPermissions).map((slug) => ({ slug, scope: "all" }));
      if (editingRole) {
        await api.put(`/v1/permissions/roles/${editingRole.id}`, {
          name: formName,
          description: formDescription || null,
          permissions,
        });
        toast.success("Role updated");
      } else {
        await api.post("/v1/permissions/roles", {
          slug: formSlug,
          name: formName,
          description: formDescription || null,
          based_on_preset_slug: formBasedOn || null,
          permissions,
        });
        toast.success("Role created");
      }
      setDialogOpen(false);
      fetchRoles();
    } catch (err: unknown) {
      const msg = typeof err === "object" && err && "detail" in err ? String((err as Record<string, unknown>).detail) : "Failed to save role";
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (roleId: string) => {
    try {
      await api.delete(`/v1/permissions/roles/${roleId}`);
      toast.success("Role deactivated");
      fetchRoles();
    } catch {
      toast.error("Failed to delete role");
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Custom Roles</h2>
          <p className="text-sm text-muted-foreground">
            Create custom permission sets beyond the built-in tiers.
          </p>
        </div>
        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogTrigger asChild>
            <Button size="sm" onClick={openCreate}>
              <Plus className="h-3.5 w-3.5 mr-1.5" />
              Create Role
            </Button>
          </DialogTrigger>
          <DialogContent className="max-w-3xl max-h-[85vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>
                {editingRole ? `Edit: ${editingRole.name}` : "Create Custom Role"}
              </DialogTitle>
            </DialogHeader>
            <div className="space-y-4 mt-2">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <Label>Name</Label>
                  <Input
                    value={formName}
                    onChange={(e) => handleNameChange(e.target.value)}
                    placeholder="e.g., Senior Technician"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label>Slug</Label>
                  <Input
                    value={formSlug}
                    onChange={(e) => setFormSlug(e.target.value)}
                    placeholder="e.g., senior_technician"
                    disabled={!!editingRole}
                    className={editingRole ? "opacity-60" : ""}
                  />
                </div>
              </div>
              <div className="space-y-1.5">
                <Label>Description</Label>
                <Input
                  value={formDescription}
                  onChange={(e) => setFormDescription(e.target.value)}
                  placeholder="Optional description"
                />
              </div>
              {!editingRole && (
                <div className="space-y-1.5">
                  <Label>Start from preset</Label>
                  <Select value={formBasedOn} onValueChange={handleBasedOnChange}>
                    <SelectTrigger>
                      <SelectValue placeholder="Start from scratch" />
                    </SelectTrigger>
                    <SelectContent>
                      {presets.map((p) => (
                        <SelectItem key={p.slug} value={p.slug}>
                          {PRESET_LABELS[p.slug] || p.name} ({p.permissions.length} permissions)
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )}
              {catalog && (
                <>
                  <div className="flex items-center justify-between">
                    <Label>Permissions</Label>
                    <span className="text-xs text-muted-foreground">
                      {formPermissions.size} selected
                    </span>
                  </div>
                  <PermissionEditor
                    catalog={catalog}
                    selected={formPermissions}
                    onChange={setFormPermissions}
                  />
                </>
              )}
              <div className="flex justify-end gap-2 pt-2">
                <Button variant="ghost" onClick={() => setDialogOpen(false)}>
                  Cancel
                </Button>
                <Button onClick={handleSave} disabled={saving}>
                  {saving && <Loader2 className="h-4 w-4 animate-spin mr-1.5" />}
                  {editingRole ? "Save Changes" : "Create Role"}
                </Button>
              </div>
            </div>
          </DialogContent>
        </Dialog>
      </div>

      {roles.length === 0 ? (
        <Card className="shadow-sm">
          <CardContent className="py-8 text-center">
            <p className="text-sm text-muted-foreground">
              No custom roles yet. Create one to define permissions beyond the built-in tiers.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-3">
          {roles.map((role) => (
            <Card key={role.id} className="shadow-sm">
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <CardTitle className="text-base">{role.name}</CardTitle>
                    <Badge variant="secondary" className="text-[10px]">
                      {role.permissions.length} permissions
                    </Badge>
                  </div>
                  <div className="flex items-center gap-1">
                    <Button variant="ghost" size="icon" onClick={() => openEdit(role)}>
                      <Pencil className="h-3.5 w-3.5" />
                    </Button>
                    <AlertDialog>
                      <AlertDialogTrigger asChild>
                        <Button variant="ghost" size="icon">
                          <Trash2 className="h-3.5 w-3.5 text-destructive" />
                        </Button>
                      </AlertDialogTrigger>
                      <AlertDialogContent>
                        <AlertDialogHeader>
                          <AlertDialogTitle>Deactivate role?</AlertDialogTitle>
                          <AlertDialogDescription>
                            This will deactivate &ldquo;{role.name}&rdquo;. Users assigned to this role will lose their custom permissions.
                          </AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                          <AlertDialogCancel>Cancel</AlertDialogCancel>
                          <AlertDialogAction
                            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                            onClick={() => handleDelete(role.id)}
                          >
                            Deactivate
                          </AlertDialogAction>
                        </AlertDialogFooter>
                      </AlertDialogContent>
                    </AlertDialog>
                  </div>
                </div>
              </CardHeader>
              {role.description && (
                <CardContent className="pt-0 pb-3">
                  <p className="text-sm text-muted-foreground">{role.description}</p>
                </CardContent>
              )}
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
