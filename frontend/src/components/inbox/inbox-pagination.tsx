"use client";

import { Button } from "@/components/ui/button";
import { ChevronLeft, ChevronRight } from "lucide-react";

interface InboxPaginationProps {
  page: number;
  totalPages: number;
  total: number;
  pageSize: number;
  onPageChange: (page: number) => void;
}

export function InboxPagination({ page, totalPages, total, pageSize, onPageChange }: InboxPaginationProps) {
  if (totalPages <= 1) return null;

  return (
    <div className="flex items-center justify-between text-sm text-muted-foreground">
      <span>
        {page * pageSize + 1}–{Math.min((page + 1) * pageSize, total)} of {total}
      </span>
      <div className="flex items-center gap-1">
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          disabled={page === 0}
          onClick={() => onPageChange(page - 1)}
        >
          <ChevronLeft className="h-4 w-4" />
        </Button>
        {Array.from({ length: totalPages }, (_, i) => {
          if (i === 0 || i === totalPages - 1 || Math.abs(i - page) <= 1) {
            return (
              <Button
                key={i}
                variant={i === page ? "default" : "ghost"}
                size="icon"
                className="h-8 w-8 text-xs"
                onClick={() => onPageChange(i)}
              >
                {i + 1}
              </Button>
            );
          }
          if (i === 1 && page > 2) return <span key={i} className="px-1">...</span>;
          if (i === totalPages - 2 && page < totalPages - 3) return <span key={i} className="px-1">...</span>;
          return null;
        })}
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          disabled={page >= totalPages - 1}
          onClick={() => onPageChange(page + 1)}
        >
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
