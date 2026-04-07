"use client";

import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Code2, CheckCircle2, Clock, Loader2 } from "lucide-react";
import { formatRelativeDate } from "@/lib/format";
import { TeamMember, ROLE_LABELS, roleBadgeVariant } from "./types";

interface TeamTableProps {
  members: TeamMember[];
  loading: boolean;
  onSelectMember: (member: TeamMember) => void;
}

export function TeamTable({ members, loading, onSelectMember }: TeamTableProps) {
  return (
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
                onClick={() => onSelectMember(m)}
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
                  {formatRelativeDate(m.last_login)}
                </TableCell>
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
    </div>
  );
}
