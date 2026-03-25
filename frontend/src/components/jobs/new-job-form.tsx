"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Card,
  CardContent,
} from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";
import { ClientPropertySearch } from "@/components/jobs/client-property-search";
import { useTeamMembers, ACTION_TYPES } from "@/hooks/use-team-members";

interface NewJobFormProps {
  onCreated: () => void;
  onClose: () => void;
}

export function NewJobForm({ onCreated, onClose }: NewJobFormProps) {
  const teamMembers = useTeamMembers();
  const [newAction, setNewAction] = useState({
    action_type: "follow_up",
    description: "",
    assigned_to: "",
    due_days: "",
    customer_name: "",
    property_address: "",
  });

  return (
    <>
      <div className="fixed inset-0 z-30" onClick={onClose} />
      <Card className="shadow-sm relative z-40">
        <CardContent className="py-3 px-4 space-y-3">
          <Input
            value={newAction.description}
            onChange={(e) =>
              setNewAction({
                ...newAction,
                description: e.target.value,
              })
            }
            placeholder="What needs to be done?"
            className="text-sm"
            autoFocus
          />
          <Select
            value={newAction.action_type}
            onValueChange={(v) => setNewAction({ ...newAction, action_type: v })}
          >
            <SelectTrigger className="h-8 text-sm w-40">
              <SelectValue placeholder="Job type..." />
            </SelectTrigger>
            <SelectContent>
              {ACTION_TYPES.map((t) => (
                <SelectItem key={t} value={t} className="text-sm capitalize">{t.replace("_", " ")}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <ClientPropertySearch
            customerName={newAction.customer_name}
            propertyAddress={newAction.property_address}
            onChange={(name, addr) =>
              setNewAction({
                ...newAction,
                customer_name: name,
                property_address: addr,
              })
            }
          />
          <div className="flex flex-wrap gap-2 items-end">
            <div className="w-48">
              <Select
                value={newAction.assigned_to || ""}
                onValueChange={(v) =>
                  setNewAction({ ...newAction, assigned_to: v })
                }
              >
                <SelectTrigger className="h-8 text-sm">
                  <SelectValue placeholder="Assign..." />
                </SelectTrigger>
                <SelectContent>
                  {teamMembers.map((name) => (
                    <SelectItem
                      key={name}
                      value={name}
                      className="text-sm"
                    >
                      {name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="w-36">
              <Input
                type="date"
                value={newAction.due_days}
                onChange={(e) =>
                  setNewAction({
                    ...newAction,
                    due_days: e.target.value,
                  })
                }
                className="h-8 text-sm"
              />
            </div>
          </div>
          <div className="flex gap-2">
            <Button
              size="sm"
              disabled={!newAction.description.trim()}
              onClick={async () => {
                const dueDate = newAction.due_days
                  ? new Date(newAction.due_days + "T23:59:59").toISOString()
                  : undefined;
                try {
                  await api.post("/v1/admin/agent-actions", {
                    action_type: newAction.action_type,
                    description: newAction.description,
                    assigned_to: newAction.assigned_to || undefined,
                    due_date: dueDate,
                    customer_name: newAction.customer_name || undefined,
                    property_address: newAction.property_address || undefined,
                  });
                  onCreated();
                  toast.success("Job created");
                } catch { toast.error("Failed to create"); }
              }}
            >
              Create
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={onClose}
            >
              Cancel
            </Button>
          </div>
        </CardContent>
      </Card>
    </>
  );
}
