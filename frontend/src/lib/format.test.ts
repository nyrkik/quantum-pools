/**
 * formatTime / formatRelativeDate — regression guard for the
 * inbox-date-ambiguity bug. Gmail / Apple Mail / Outlook all
 * include the year for prior-year messages so a March 2025 thread
 * doesn't look like a March 2026 thread. If that disambiguation
 * regresses, a stale inbox row silently misleads the user about
 * when the message arrived.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { formatTime, formatRelativeDate } from "./format";

describe("formatTime — year disambiguation", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-04-20T12:00:00Z"));
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("omits year for a date in the current year", () => {
    // March 22, 2026 — current year — no year shown.
    expect(formatTime("2026-03-22T15:00:00Z")).toMatch(/^Mar 22$/);
  });

  it("INCLUDES year for a prior-year date (Bill Hoge regression)", () => {
    // March 22, 2025 — last year — year must appear so the row
    // doesn't silently look brand new.
    expect(formatTime("2025-03-22T15:00:00Z")).toMatch(/^Mar 22, 2025$/);
  });

  it("INCLUDES year for a date 18+ months old", () => {
    expect(formatTime("2024-10-01T15:00:00Z")).toMatch(/2024/);
  });

  it("still uses relative time for very recent", () => {
    expect(formatTime("2026-04-20T11:00:00Z")).toBe("1h ago");
  });
});

describe("formatRelativeDate — year disambiguation", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-04-20T12:00:00Z"));
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("includes year for prior-year fallback", () => {
    expect(formatRelativeDate("2025-01-10T12:00:00Z")).toMatch(/2025/);
  });

  it("omits year for current-year fallback", () => {
    // Within this year, > 7 days ago → date only, no year.
    expect(formatRelativeDate("2026-01-10T12:00:00Z")).toMatch(/^Jan 10$/);
  });
});
