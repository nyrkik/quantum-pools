"use client";

import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Plus, Trash2, Loader2, Check, X, ShieldBan, Route } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
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
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";

interface RoutingRule {
  id: string;
  address_pattern: string;
  match_type: string;
  action: string;
  match_field: string;
  category: string | null;
  required_permission: string | null;
  priority: number;
  is_active: boolean;
  created_at: string;
}

interface PermissionItem {
  slug: string;
  action: string;
  description: string | null;
}

interface PermissionCatalog {
  resources: Record<string, PermissionItem[]>;
}

const CATEGORIES = ["service", "billing", "sales", "admin", "general"];

export function InboxRoutingSection({ editMode }: { editMode: boolean }) {
  const [rules, setRules] = useState<RoutingRule[]>([]);
  const [permSlugs, setPermSlugs] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState(false);
  const [saving, setSaving] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState("route");

  // New rule form
  const [newRule, setNewRule] = useState({
    address_pattern: "",
    match_type: "exact",
    action: "route",
    match_field: "to",
    category: "",
    required_permission: "",
    priority: 0,
  });

  const loadRules = useCallback(() => {
    setLoading(true);
    api
      .get<RoutingRule[]>("/v1/inbox-routing-rules")
      .then(setRules)
      .catch(() => toast.error("Failed to load routing rules"))
      .finally(() => setLoading(false));
  }, []);

  const loadPermissions = useCallback(() => {
    api
      .get<PermissionCatalog>("/v1/permissions/catalog")
      .then((data) => {
        const slugs: string[] = [];
        for (const perms of Object.values(data.resources)) {
          for (const p of perms) {
            slugs.push(p.slug);
          }
        }
        setPermSlugs(slugs.sort());
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    loadRules();
    loadPermissions();
  }, [loadRules, loadPermissions]);

  const handleCreate = async () => {
    if (!newRule.address_pattern.trim()) {
      toast.error("Address pattern is required");
      return;
    }
    setSaving("new");
    try {
      await api.post("/v1/inbox-routing-rules", {
        address_pattern: newRule.address_pattern.trim(),
        match_type: newRule.match_type,
        action: newRule.action,
        match_field: newRule.match_field,
        category: newRule.category || null,
        required_permission: newRule.required_permission || null,
        priority: newRule.priority,
        is_active: true,
      });
      toast.success("Rule created");
      setAdding(false);
      setNewRule({ address_pattern: "", match_type: "exact", action: "route", match_field: "to", category: "", required_permission: "", priority: 0 });
      loadRules();
    } catch {
      toast.error("Failed to create rule");
    } finally {
      setSaving(null);
    }
  };

  const handleToggle = async (rule: RoutingRule) => {
    setSaving(rule.id);
    try {
      await api.put(`/v1/inbox-routing-rules/${rule.id}`, {
        is_active: !rule.is_active,
      });
      setRules((prev) =>
        prev.map((r) => (r.id === rule.id ? { ...r, is_active: !r.is_active } : r))
      );
    } catch {
      toast.error("Failed to update rule");
    } finally {
      setSaving(null);
    }
  };

  const handleDelete = async (id: string) => {
    setSaving(id);
    try {
      await api.delete(`/v1/inbox-routing-rules/${id}`);
      toast.success("Rule deleted");
      loadRules();
    } catch {
      toast.error("Failed to delete rule");
    } finally {
      setSaving(null);
    }
  };

  const handleUpdate = async (id: string, field: string, value: string | number | null) => {
    setSaving(id);
    try {
      await api.put(`/v1/inbox-routing-rules/${id}`, { [field]: value });
      loadRules();
    } catch {
      toast.error("Failed to update rule");
    } finally {
      setSaving(null);
    }
  };

  const routeRules = rules.filter((r) => r.action === "route");
  const blockRules = rules.filter((r) => r.action === "block");

  const renderRulesTable = (filtered: RoutingRule[], isBlockTab: boolean) => {
    if (filtered.length === 0 && !adding) {
      return (
        <p className="text-sm text-muted-foreground text-center py-6">
          {isBlockTab
            ? "No block rules configured. All senders will be processed."
            : "No routing rules configured. All emails will be visible to everyone with inbox access."}
        </p>
      );
    }

    return (
      <Table>
        <TableHeader>
          <TableRow className="bg-slate-100 dark:bg-slate-800">
            <TableHead className="text-xs font-medium uppercase tracking-wide">Pattern</TableHead>
            <TableHead className="text-xs font-medium uppercase tracking-wide w-[90px]">Match</TableHead>
            {!isBlockTab && (
              <>
                <TableHead className="text-xs font-medium uppercase tracking-wide">Category</TableHead>
                <TableHead className="text-xs font-medium uppercase tracking-wide">Permission</TableHead>
              </>
            )}
            <TableHead className="text-xs font-medium uppercase tracking-wide w-[60px]">Priority</TableHead>
            <TableHead className="text-xs font-medium uppercase tracking-wide w-[60px]">Active</TableHead>
            {editMode && <TableHead className="text-xs font-medium uppercase tracking-wide w-[40px]" />}
          </TableRow>
        </TableHeader>
        <TableBody>
          {filtered.map((rule, idx) => (
            <TableRow
              key={rule.id}
              className={`${
                idx % 2 === 1 ? "bg-slate-50 dark:bg-slate-900" : ""
              } hover:bg-blue-50 dark:hover:bg-blue-950`}
            >
              <TableCell className="text-sm font-mono">
                {editMode ? (
                  <Input
                    className="h-7 text-sm font-mono"
                    defaultValue={rule.address_pattern}
                    onBlur={(e) => {
                      if (e.target.value !== rule.address_pattern) {
                        handleUpdate(rule.id, "address_pattern", e.target.value);
                      }
                    }}
                  />
                ) : (
                  rule.address_pattern
                )}
              </TableCell>
              <TableCell className="text-sm">
                {editMode ? (
                  <Select
                    defaultValue={rule.match_type}
                    onValueChange={(v) => handleUpdate(rule.id, "match_type", v)}
                  >
                    <SelectTrigger className="h-7 text-xs w-[90px]">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="exact">Exact</SelectItem>
                      <SelectItem value="contains">Contains</SelectItem>
                    </SelectContent>
                  </Select>
                ) : (
                  <Badge variant="outline" className="text-[10px]">{rule.match_type}</Badge>
                )}
              </TableCell>
              {!isBlockTab && (
                <>
                  <TableCell className="text-sm">
                    {editMode ? (
                      <Select
                        defaultValue={rule.category || "__none__"}
                        onValueChange={(v) => handleUpdate(rule.id, "category", v === "__none__" ? null : v)}
                      >
                        <SelectTrigger className="h-7 text-xs w-[100px]">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="__none__">None</SelectItem>
                          {CATEGORIES.map((c) => (
                            <SelectItem key={c} value={c}>{c.charAt(0).toUpperCase() + c.slice(1)}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    ) : (
                      rule.category ? (
                        <Badge variant="secondary" className="text-[10px]">{rule.category}</Badge>
                      ) : (
                        <span className="text-muted-foreground text-xs">-</span>
                      )
                    )}
                  </TableCell>
                  <TableCell className="text-sm">
                    {editMode ? (
                      <Select
                        defaultValue={rule.required_permission || "__everyone__"}
                        onValueChange={(v) =>
                          handleUpdate(rule.id, "required_permission", v === "__everyone__" ? null : v)
                        }
                      >
                        <SelectTrigger className="h-7 text-xs w-[160px]">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="__everyone__">Everyone</SelectItem>
                          {permSlugs.map((s) => (
                            <SelectItem key={s} value={s}>{s}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    ) : rule.required_permission ? (
                      <code className="text-xs bg-muted px-1.5 py-0.5 rounded">{rule.required_permission}</code>
                    ) : (
                      <span className="text-muted-foreground text-xs">Everyone</span>
                    )}
                  </TableCell>
                </>
              )}
              <TableCell className="text-sm text-center">
                {editMode ? (
                  <Input
                    type="number"
                    className="h-7 text-sm w-[60px]"
                    defaultValue={rule.priority}
                    onBlur={(e) => {
                      const val = parseInt(e.target.value);
                      if (!isNaN(val) && val !== rule.priority) {
                        handleUpdate(rule.id, "priority", val);
                      }
                    }}
                  />
                ) : (
                  rule.priority
                )}
              </TableCell>
              <TableCell>
                <Switch
                  checked={rule.is_active}
                  onCheckedChange={() => editMode && handleToggle(rule)}
                  disabled={!editMode || saving === rule.id}
                  className="scale-75"
                />
              </TableCell>
              {editMode && (
                <TableCell>
                  <AlertDialog>
                    <AlertDialogTrigger asChild>
                      <Button variant="ghost" size="icon" className="h-7 w-7">
                        <Trash2 className="h-3.5 w-3.5 text-destructive" />
                      </Button>
                    </AlertDialogTrigger>
                    <AlertDialogContent>
                      <AlertDialogHeader>
                        <AlertDialogTitle>Delete rule?</AlertDialogTitle>
                        <AlertDialogDescription>
                          This will permanently remove the rule for{" "}
                          <strong>{rule.address_pattern}</strong>.
                          {!isBlockTab && " Existing threads will keep their current visibility."}
                        </AlertDialogDescription>
                      </AlertDialogHeader>
                      <AlertDialogFooter>
                        <AlertDialogCancel>Cancel</AlertDialogCancel>
                        <AlertDialogAction onClick={() => handleDelete(rule.id)}>
                          Delete
                        </AlertDialogAction>
                      </AlertDialogFooter>
                    </AlertDialogContent>
                  </AlertDialog>
                </TableCell>
              )}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    );
  };

  return (
    <Card className="shadow-sm">
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-base">Inbox Rules</CardTitle>
            <CardDescription>
              Route emails to team members or block automated senders.
              Rules match by priority (lower = first).
            </CardDescription>
          </div>
          {editMode && (
            <Button size="sm" variant="outline" onClick={() => {
              setNewRule((prev) => ({
                ...prev,
                action: activeTab === "block" ? "block" : "route",
                match_field: activeTab === "block" ? "from" : "to",
              }));
              setAdding(true);
            }}>
              <Plus className="h-3.5 w-3.5 mr-1" />
              Add Rule
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="flex justify-center py-8">
            <Loader2 className="h-5 w-5 animate-spin" />
          </div>
        ) : (
          <div className="space-y-4">
            {/* Add new rule form */}
            {adding && (
              <div className="rounded-lg border border-primary/30 bg-muted/50 p-4 space-y-3">
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <div className="space-y-1">
                    <Label className="text-xs">Address Pattern</Label>
                    <Input
                      className="h-8 text-sm"
                      placeholder={newRule.action === "block" ? "spammer.com" : "accounting@company.com"}
                      value={newRule.address_pattern}
                      onChange={(e) => setNewRule({ ...newRule, address_pattern: e.target.value })}
                    />
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs">Action</Label>
                    <Select
                      value={newRule.action}
                      onValueChange={(v) => setNewRule({
                        ...newRule,
                        action: v,
                        match_field: v === "block" ? "from" : "to",
                      })}
                    >
                      <SelectTrigger className="h-8 text-sm">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="route">Route</SelectItem>
                        <SelectItem value="block">Block</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs">Match On</Label>
                    <Select
                      value={newRule.match_field}
                      onValueChange={(v) => setNewRule({ ...newRule, match_field: v })}
                    >
                      <SelectTrigger className="h-8 text-sm">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="to">Incoming address</SelectItem>
                        <SelectItem value="from">Sender</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs">Match Type</Label>
                    <Select
                      value={newRule.match_type}
                      onValueChange={(v) => setNewRule({ ...newRule, match_type: v })}
                    >
                      <SelectTrigger className="h-8 text-sm">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="exact">Exact</SelectItem>
                        <SelectItem value="contains">Contains</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  {newRule.action === "route" && (
                    <>
                      <div className="space-y-1">
                        <Label className="text-xs">Category</Label>
                        <Select
                          value={newRule.category || "__none__"}
                          onValueChange={(v) => setNewRule({ ...newRule, category: v === "__none__" ? "" : v })}
                        >
                          <SelectTrigger className="h-8 text-sm">
                            <SelectValue placeholder="None" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="__none__">None</SelectItem>
                            {CATEGORIES.map((c) => (
                              <SelectItem key={c} value={c}>
                                {c.charAt(0).toUpperCase() + c.slice(1)}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="space-y-1">
                        <Label className="text-xs">Required Permission</Label>
                        <Select
                          value={newRule.required_permission || "__everyone__"}
                          onValueChange={(v) =>
                            setNewRule({ ...newRule, required_permission: v === "__everyone__" ? "" : v })
                          }
                        >
                          <SelectTrigger className="h-8 text-sm">
                            <SelectValue placeholder="Everyone" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="__everyone__">Everyone (no restriction)</SelectItem>
                            {permSlugs.map((s) => (
                              <SelectItem key={s} value={s}>
                                {s}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                    </>
                  )}
                  <div className="space-y-1">
                    <Label className="text-xs">Priority</Label>
                    <Input
                      type="number"
                      className="h-8 text-sm max-w-[100px]"
                      value={newRule.priority}
                      onChange={(e) => setNewRule({ ...newRule, priority: parseInt(e.target.value) || 0 })}
                    />
                  </div>
                </div>
                <div className="flex gap-2 justify-end">
                  <Button size="sm" variant="ghost" onClick={() => setAdding(false)}>
                    Cancel
                  </Button>
                  <Button size="sm" onClick={handleCreate} disabled={saving === "new"}>
                    {saving === "new" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5 mr-1" />}
                    Create
                  </Button>
                </div>
              </div>
            )}

            {/* Tabbed view: Route vs Block */}
            <Tabs defaultValue="route" onValueChange={setActiveTab}>
              <TabsList>
                <TabsTrigger value="route" className="text-xs">
                  <Route className="h-3.5 w-3.5 mr-1" />
                  Route ({routeRules.length})
                </TabsTrigger>
                <TabsTrigger value="block" className="text-xs">
                  <ShieldBan className="h-3.5 w-3.5 mr-1" />
                  Block ({blockRules.length})
                </TabsTrigger>
              </TabsList>
              <TabsContent value="route" className="mt-3">
                {renderRulesTable(routeRules, false)}
              </TabsContent>
              <TabsContent value="block" className="mt-3">
                {renderRulesTable(blockRules, true)}
              </TabsContent>
            </Tabs>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
