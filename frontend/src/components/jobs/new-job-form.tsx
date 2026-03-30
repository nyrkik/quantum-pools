"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Overlay, OverlayContent, OverlayHeader, OverlayTitle, OverlayBody, OverlayFooter } from "@/components/ui/overlay";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";
import { Plus, Trash2 } from "lucide-react";
import { ClientPropertySearch } from "@/components/jobs/client-property-search";
import { useTeamMembers, ACTION_TYPES } from "@/hooks/use-team-members";

interface NewJobFormProps {
  open: boolean;
  onCreated: () => void;
  onClose: () => void;
}

interface LineItem {
  description: string;
  quantity: number;
  unit_price: number;
}

export function NewJobForm({ open, onCreated, onClose }: NewJobFormProps) {
  const teamMembers = useTeamMembers();
  const [jobPath, setJobPath] = useState<"internal" | "customer">("internal");
  const [newAction, setNewAction] = useState({
    action_type: "",
    description: "",
    assigned_to: "",
    due_days: "",
    customer_name: "",
    property_address: "",
  });
  const [lineItems, setLineItems] = useState<LineItem[]>([
    { description: "", quantity: 1, unit_price: 0 },
  ]);

  const addLineItem = () => {
    setLineItems([...lineItems, { description: "", quantity: 1, unit_price: 0 }]);
  };

  const updateLineItem = (idx: number, field: keyof LineItem, value: string | number) => {
    setLineItems(lineItems.map((li, i) =>
      i === idx ? { ...li, [field]: value } : li
    ));
  };

  const removeLineItem = (idx: number) => {
    if (lineItems.length <= 1) return;
    setLineItems(lineItems.filter((_, i) => i !== idx));
  };

  const estimateTotal = lineItems.reduce((sum, li) => sum + li.quantity * li.unit_price, 0);

  const handleCreate = async () => {
    const dueDate = newAction.due_days
      ? new Date(newAction.due_days + "T23:59:59").toISOString()
      : undefined;

    const body: Record<string, unknown> = {
      action_type: newAction.action_type,
      description: newAction.description,
      assigned_to: newAction.assigned_to || undefined,
      due_date: dueDate,
      customer_name: newAction.customer_name || undefined,
      property_address: newAction.property_address || undefined,
      job_path: jobPath,
    };

    if (jobPath === "customer") {
      const validItems = lineItems.filter((li) => li.description.trim());
      if (validItems.length > 0) {
        body.line_items = validItems;
      }
    }

    try {
      await api.post("/v1/admin/agent-actions", body);
      onCreated();
      toast.success(jobPath === "customer" ? "Job created with draft estimate" : "Job created");
    } catch {
      toast.error("Failed to create");
    }
  };

  return (
    <Overlay open={open} onOpenChange={(o) => { if (!o) onClose(); }}>
      <OverlayContent>
        <OverlayHeader>
          <OverlayTitle>New Job</OverlayTitle>
        </OverlayHeader>
        <OverlayBody className="space-y-3">
          {/* Path toggle + job type */}
          <div className="flex items-center gap-2">
            <div className="flex gap-1 bg-muted p-0.5 rounded-md">
              <button
                onClick={() => setJobPath("internal")}
                className={`px-3 py-1 text-xs rounded transition-colors ${
                  jobPath === "internal" ? "bg-background shadow-sm font-medium" : "text-muted-foreground"
                }`}
              >
                Internal
              </button>
              <button
                onClick={() => setJobPath("customer")}
                className={`px-3 py-1 text-xs rounded transition-colors ${
                  jobPath === "customer" ? "bg-background shadow-sm font-medium" : "text-muted-foreground"
                }`}
              >
                Customer
              </button>
            </div>
            <Select
              value={newAction.action_type}
              onValueChange={(v) => setNewAction({ ...newAction, action_type: v })}
            >
              <SelectTrigger className="h-8 text-sm w-40 capitalize">
                <SelectValue placeholder="Select type *" />
              </SelectTrigger>
              <SelectContent>
                {ACTION_TYPES.map((t) => (
                  <SelectItem key={t} value={t} className="text-sm capitalize">{t.replace(/_/g, " ")}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <Input
            value={newAction.description}
            onChange={(e) => setNewAction({ ...newAction, description: e.target.value })}
            placeholder="Description"
            className="text-sm"
            autoFocus
          />

          <ClientPropertySearch
            customerName={newAction.customer_name}
            propertyAddress={newAction.property_address}
            onChange={(name, addr) => setNewAction({ ...newAction, customer_name: name, property_address: addr })}
          />

          <div className="flex flex-wrap gap-2 items-end">
            <div className="flex-1 min-w-[200px]">
              <Select
                value={newAction.assigned_to || ""}
                onValueChange={(v) => setNewAction({ ...newAction, assigned_to: v })}
              >
                <SelectTrigger className="h-9 text-sm">
                  <SelectValue placeholder="Assign to..." />
                </SelectTrigger>
                <SelectContent>
                  {teamMembers.map((name) => (
                    <SelectItem key={name} value={name} className="text-sm">{name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="w-36">
              <Input
                type="date"
                value={newAction.due_days}
                onChange={(e) => setNewAction({ ...newAction, due_days: e.target.value })}
                className="h-8 text-sm"
              />
            </div>
          </div>

          {/* Line items — customer path only */}
          {jobPath === "customer" && (
            <div className="space-y-2 border-t pt-3">
              <p className="text-xs text-muted-foreground uppercase tracking-wide font-medium">Estimate Line Items</p>
              {lineItems.map((li, idx) => (
                <div key={idx} className="flex items-center gap-2">
                  <Input
                    value={li.description}
                    onChange={(e) => updateLineItem(idx, "description", e.target.value)}
                    placeholder="Description"
                    className="h-8 text-sm flex-1"
                  />
                  <Input
                    type="number"
                    value={li.quantity || ""}
                    onChange={(e) => updateLineItem(idx, "quantity", parseFloat(e.target.value) || 0)}
                    className="h-8 text-sm w-16 text-center"
                    min={1}
                  />
                  <Input
                    type="number"
                    value={li.unit_price || ""}
                    onChange={(e) => updateLineItem(idx, "unit_price", parseFloat(e.target.value) || 0)}
                    placeholder="$"
                    className="h-8 text-sm w-24"
                    step="0.01"
                  />
                  {lineItems.length > 1 && (
                    <Button variant="ghost" size="icon" className="h-8 w-8 text-destructive shrink-0" onClick={() => removeLineItem(idx)}>
                      <Trash2 className="h-3 w-3" />
                    </Button>
                  )}
                </div>
              ))}
              <div className="flex items-center justify-between">
                <Button variant="outline" size="sm" className="h-7 text-xs gap-1" onClick={addLineItem}>
                  <Plus className="h-3 w-3" /> Add Line
                </Button>
                {estimateTotal > 0 && (
                  <span className="text-sm font-medium">Total: ${estimateTotal.toFixed(2)}</span>
                )}
              </div>
            </div>
          )}

        </OverlayBody>
        <OverlayFooter>
          <Button
            className="flex-1"
            disabled={!newAction.description.trim() || !newAction.action_type}
            onClick={handleCreate}
          >
            {jobPath === "customer" ? "Create + Draft Estimate" : "Create Job"}
          </Button>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
        </OverlayFooter>
      </OverlayContent>
    </Overlay>
  );
}
