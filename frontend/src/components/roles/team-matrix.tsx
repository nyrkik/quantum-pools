"use client";

import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Loader2, ChevronDown, ChevronUp, Pencil, Check, Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
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
} from "@/components/ui/dialog";
import { PermissionEditor, type PermissionCatalog } from "./permission-editor";

interface TeamMatrixMember {
  user_id: string;
  org_user_id: string;
  name: string;
  email: string;
  job_title: string | null;
  role: string;
  org_role_name: string | null;
  permission_count: number;
  overrides_count: number;
  effective_permissions: Record<string, string>;
}

interface OverrideItem {
  slug: string;
  scope: string;
  granted: boolean;
}

const ROLE_LABELS: Record<string, string> = {
  owner: "Full Access",
  admin: "Admin",
  manager: "Standard",
  technician: "Limited",
  readonly: "View Only",
  custom: "Custom",
};

const ROLE_ORDER = ["owner", "admin", "manager", "technician", "readonly", "custom"];

const ROLE_BADGE_VARIANTS: Record<string, "default" | "secondary" | "outline"> = {
  owner: "default",
  admin: "default",
  manager: "secondary",
  technician: "outline",
  readonly: "outline",
  custom: "secondary",
};

interface TeamMatrixProps {
  catalog: PermissionCatalog | null;
}

export function TeamMatrix({ catalog }: TeamMatrixProps) {
  const [members, setMembers] = useState<TeamMatrixMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedUser, setExpandedUser] = useState<string | null>(null);
  const [editingUser, setEditingUser] = useState<TeamMatrixMember | null>(null);
  const [overridePerms, setOverridePerms] = useState<Set<string>>(new Set());
  const [basePerms, setBasePerms] = useState<Set<string>>(new Set());
  const [saving, setSaving] = useState(false);

  const fetchMatrix = useCallback(async () => {
    try {
      const data = await api.get<TeamMatrixMember[]>("/v1/permissions/team-matrix");
      setMembers(data);
    } catch {
      toast.error("Failed to load team matrix");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchMatrix();
  }, [fetchMatrix]);

  const openOverrideEditor = async (member: TeamMatrixMember) => {
    // Fetch current overrides to distinguish base from overridden
    try {
      const overrides = await api.get<{ overrides: OverrideItem[] }>(
        `/v1/permissions/users/${member.org_user_id}/overrides`
      );
      // Base = effective minus granted overrides, plus revoked overrides
      const grantedOverrides = new Set(
        overrides.overrides.filter((o) => o.granted).map((o) => o.slug)
      );
      const revokedOverrides = new Set(
        overrides.overrides.filter((o) => !o.granted).map((o) => o.slug)
      );

      // Compute base permissions (what they'd have without overrides)
      const base = new Set<string>();
      for (const slug of Object.keys(member.effective_permissions)) {
        if (!grantedOverrides.has(slug)) {
          base.add(slug);
        }
      }
      for (const slug of revokedOverrides) {
        base.add(slug);
      }
      setBasePerms(base);
      setOverridePerms(new Set(Object.keys(member.effective_permissions)));
      setEditingUser(member);
    } catch {
      toast.error("Failed to load user overrides");
    }
  };

  const saveOverrides = async () => {
    if (!editingUser) return;
    setSaving(true);
    try {
      // Compute delta from base
      const overrides: OverrideItem[] = [];
      // Added: in selected but not in base
      for (const slug of overridePerms) {
        if (!basePerms.has(slug)) {
          overrides.push({ slug, scope: "all", granted: true });
        }
      }
      // Revoked: in base but not in selected
      for (const slug of basePerms) {
        if (!overridePerms.has(slug)) {
          overrides.push({ slug, scope: "all", granted: false });
        }
      }

      await api.put(`/v1/permissions/users/${editingUser.org_user_id}/overrides`, overrides);
      toast.success(`Overrides saved for ${editingUser.name}`);
      setEditingUser(null);
      fetchMatrix();
    } catch {
      toast.error("Failed to save overrides");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  // Sort by role order
  const sorted = [...members].sort(
    (a, b) => ROLE_ORDER.indexOf(a.role) - ROLE_ORDER.indexOf(b.role)
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Users className="h-5 w-5 text-muted-foreground" />
        <h2 className="text-lg font-semibold">Team Access</h2>
        <Badge variant="secondary" className="text-xs">{members.length} members</Badge>
      </div>
      <p className="text-sm text-muted-foreground">
        See who has access to what. Click a row to view effective permissions, or edit overrides.
      </p>

      <Card className="shadow-sm overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow className="bg-slate-100 dark:bg-slate-800">
              <TableHead className="text-xs font-medium uppercase tracking-wide">Name</TableHead>
              <TableHead className="text-xs font-medium uppercase tracking-wide">Role</TableHead>
              <TableHead className="text-xs font-medium uppercase tracking-wide text-center hidden sm:table-cell">Permissions</TableHead>
              <TableHead className="text-xs font-medium uppercase tracking-wide text-center hidden sm:table-cell">Overrides</TableHead>
              <TableHead className="text-xs font-medium uppercase tracking-wide text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {sorted.map((member, idx) => {
              const isExpanded = expandedUser === member.org_user_id;
              return (
                <TableRow
                  key={member.org_user_id}
                  className={idx % 2 === 1 ? "bg-slate-50 dark:bg-slate-900" : ""}
                >
                  <TableCell>
                    <div>
                      <p className="text-sm font-medium">{member.name}</p>
                      <p className="text-xs text-muted-foreground">
                        {member.job_title || member.email}
                      </p>
                    </div>
                  </TableCell>
                  <TableCell>
                    <Badge variant={ROLE_BADGE_VARIANTS[member.role] || "outline"}>
                      {member.org_role_name || ROLE_LABELS[member.role] || member.role}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-center hidden sm:table-cell">
                    <span className="text-sm font-medium">{member.permission_count}</span>
                  </TableCell>
                  <TableCell className="text-center hidden sm:table-cell">
                    {member.overrides_count > 0 ? (
                      <Badge variant="outline" className="border-amber-400 text-amber-600 text-[10px]">
                        {member.overrides_count}
                      </Badge>
                    ) : (
                      <span className="text-xs text-muted-foreground">--</span>
                    )}
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex items-center justify-end gap-1">
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() =>
                          setExpandedUser(isExpanded ? null : member.org_user_id)
                        }
                      >
                        {isExpanded ? (
                          <ChevronUp className="h-3.5 w-3.5 text-muted-foreground" />
                        ) : (
                          <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
                        )}
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => openOverrideEditor(member)}
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </Card>

      {/* Expanded effective permissions */}
      {expandedUser && catalog && (
        <Card className="shadow-sm border-l-4 border-primary">
          <CardContent className="pt-4">
            {(() => {
              const member = members.find((m) => m.org_user_id === expandedUser);
              if (!member) return null;
              return (
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <h3 className="text-sm font-semibold">{member.name}</h3>
                      <Badge variant="secondary" className="text-[10px]">
                        {member.permission_count} effective permissions
                      </Badge>
                    </div>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => openOverrideEditor(member)}
                    >
                      <Pencil className="h-3.5 w-3.5 mr-1.5" />
                      Edit Overrides
                    </Button>
                  </div>
                  <PermissionEditor
                    catalog={catalog}
                    selected={new Set(Object.keys(member.effective_permissions))}
                    onChange={() => {}}
                    readOnly
                  />
                </div>
              );
            })()}
          </CardContent>
        </Card>
      )}

      {/* Override editor dialog */}
      <Dialog open={!!editingUser} onOpenChange={(open) => !open && setEditingUser(null)}>
        <DialogContent className="max-w-3xl max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>
              Edit Overrides: {editingUser?.name}
            </DialogTitle>
          </DialogHeader>
          {editingUser && catalog && (
            <div className="space-y-4 mt-2">
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <span>Base tier:</span>
                <Badge variant="secondary">
                  {ROLE_LABELS[editingUser.role] || editingUser.role}
                </Badge>
                <span>({basePerms.size} permissions)</span>
              </div>
              <div className="flex items-center gap-4 text-xs">
                <div className="flex items-center gap-1.5">
                  <div className="w-3 h-3 rounded bg-green-100 border border-green-400" />
                  <span className="text-muted-foreground">Added via override</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <div className="w-3 h-3 rounded bg-red-100 border border-red-400" />
                  <span className="text-muted-foreground">Revoked via override</span>
                </div>
              </div>
              <PermissionEditor
                catalog={catalog}
                selected={overridePerms}
                onChange={setOverridePerms}
                basePermissions={basePerms}
                overrideMode
              />
              <div className="flex justify-end gap-2 pt-2">
                <Button variant="ghost" onClick={() => setEditingUser(null)}>
                  Cancel
                </Button>
                <Button onClick={saveOverrides} disabled={saving}>
                  {saving ? (
                    <Loader2 className="h-4 w-4 animate-spin mr-1.5" />
                  ) : (
                    <Check className="h-4 w-4 mr-1.5" />
                  )}
                  Save Overrides
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
