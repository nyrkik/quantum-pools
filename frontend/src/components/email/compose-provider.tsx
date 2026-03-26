"use client";

import { createContext, useContext, useState, useCallback, type ReactNode } from "react";

export interface ComposeOptions {
  to?: string;
  customerId?: string;
  customerName?: string;
  subject?: string;
  body?: string;
  jobId?: string;
  onSent?: () => void;
  /** Original AI draft body — if user edits, diff is logged as correction */
  originalDraft?: string;
  originalSubject?: string;
}

interface ComposeContextValue {
  isOpen: boolean;
  isMinimized: boolean;
  options: ComposeOptions;
  openCompose: (opts?: ComposeOptions) => void;
  closeCompose: () => void;
  toggleMinimize: () => void;
}

const ComposeContext = createContext<ComposeContextValue | null>(null);

export function ComposeProvider({ children }: { children: ReactNode }) {
  const [isOpen, setIsOpen] = useState(false);
  const [isMinimized, setIsMinimized] = useState(false);
  const [options, setOptions] = useState<ComposeOptions>({});

  const openCompose = useCallback((opts?: ComposeOptions) => {
    setOptions(opts || {});
    setIsOpen(true);
    setIsMinimized(false);
  }, []);

  const closeCompose = useCallback(() => {
    setIsOpen(false);
    setIsMinimized(false);
    setOptions({});
  }, []);

  const toggleMinimize = useCallback(() => {
    setIsMinimized((prev) => !prev);
  }, []);

  return (
    <ComposeContext.Provider value={{ isOpen, isMinimized, options, openCompose, closeCompose, toggleMinimize }}>
      {children}
    </ComposeContext.Provider>
  );
}

export function useCompose(): ComposeContextValue {
  const ctx = useContext(ComposeContext);
  if (!ctx) throw new Error("useCompose must be used within ComposeProvider");
  return ctx;
}
