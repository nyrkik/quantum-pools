"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { cn } from "@/lib/utils";

export interface SectionNavItem {
  id: string;
  label: string;
  icon: React.ElementType;
}

interface SectionJumpNavProps {
  sections: SectionNavItem[];
}

export function SectionJumpNav({ sections }: SectionJumpNavProps) {
  const [activeId, setActiveId] = useState<string>(sections[0]?.id ?? "");
  const observerRef = useRef<IntersectionObserver | null>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  const handleClick = useCallback((id: string) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "start" });
    setActiveId(id);
  }, []);

  useEffect(() => {
    if (observerRef.current) observerRef.current.disconnect();

    const ratioMap = new Map<string, number>();

    observerRef.current = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          ratioMap.set(entry.target.id, entry.intersectionRatio);
        }
        // Pick the section with the highest visible ratio
        let bestId = activeId;
        let bestRatio = -1;
        for (const s of sections) {
          const ratio = ratioMap.get(s.id) ?? 0;
          if (ratio > bestRatio) {
            bestRatio = ratio;
            bestId = s.id;
          }
        }
        if (bestId && bestRatio > 0) {
          setActiveId(bestId);
        }
      },
      { threshold: [0, 0.25, 0.5, 0.75, 1], rootMargin: "-80px 0px -40% 0px" }
    );

    for (const s of sections) {
      const el = document.getElementById(s.id);
      if (el) observerRef.current.observe(el);
    }

    return () => observerRef.current?.disconnect();
  }, [sections]); // eslint-disable-line react-hooks/exhaustive-deps

  if (sections.length === 0) return null;

  return (
    <>
      {/* Desktop: vertical sidebar */}
      <nav className="hidden lg:flex flex-col gap-1 sticky top-20 w-44 shrink-0 self-start">
        {sections.map((s) => {
          const Icon = s.icon;
          const isActive = activeId === s.id;
          return (
            <button
              key={s.id}
              onClick={() => handleClick(s.id)}
              className={cn(
                "flex items-center gap-2 px-3 py-2 rounded-md text-sm transition-colors text-left",
                isActive
                  ? "bg-primary/10 text-primary font-medium"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground"
              )}
            >
              <Icon className="h-4 w-4 shrink-0" />
              <span className="truncate">{s.label}</span>
            </button>
          );
        })}
      </nav>

      {/* Mobile: horizontal scrollable pill bar */}
      <div
        ref={scrollContainerRef}
        className="lg:hidden sticky top-14 z-30 bg-background/95 backdrop-blur border-b overflow-x-auto scrollbar-hide"
      >
        <div className="flex gap-1 px-3 py-2 min-w-max">
          {sections.map((s) => {
            const Icon = s.icon;
            const isActive = activeId === s.id;
            return (
              <button
                key={s.id}
                onClick={() => handleClick(s.id)}
                className={cn(
                  "flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium whitespace-nowrap transition-colors",
                  isActive
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted text-muted-foreground hover:text-foreground"
                )}
              >
                <Icon className="h-3.5 w-3.5 shrink-0" />
                {s.label}
              </button>
            );
          })}
        </div>
      </div>
    </>
  );
}
