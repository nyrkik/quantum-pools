/**
 * Shared formatting utilities used across multiple pages.
 */

/**
 * "Mar 22" for dates in the current year, "Mar 22, 2025" for prior
 * years — avoids the Gmail/Apple Mail footgun where an old thread
 * looks brand new because only the month/day shows.
 */
function _dateWithYearIfStale(d: Date, now: Date): string {
  if (d.getFullYear() === now.getFullYear()) {
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  }
  return d.toLocaleDateString("en-US", {
    month: "short", day: "numeric", year: "numeric",
  });
}

/** Relative time: "just now", "5m ago", "2h ago", "Mar 15" (this year)
 * or "Mar 15, 2025" (older). Matches every mainstream inbox client. */
export function formatTime(iso: string | null): string {
  if (!iso) return "\u2014";
  const d = new Date(iso);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  return _dateWithYearIfStale(d, now);
}

/** Relative time with "Never" default and week-level fallback */
export function formatRelativeDate(iso: string | null): string {
  if (!iso) return "Never";
  const d = new Date(iso);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDays = Math.floor(diffHr / 24);
  if (diffDays < 7) return `${diffDays}d ago`;
  return _dateWithYearIfStale(d, now);
}

/** Full date+time: "Mar 15, 2026, 3:04 PM" */
export function formatFullDate(iso: string | null): string {
  if (!iso) return "\u2014";
  return new Date(iso).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

/** Due date relative: "2d overdue", "Due today", "Due tomorrow", "Due in 5d" */
export function formatDueDate(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  const now = new Date();
  const diffDays = Math.ceil((d.getTime() - now.getTime()) / 86400000);
  if (diffDays < 0) return `${Math.abs(diffDays)}d overdue`;
  if (diffDays === 0) return "Due today";
  if (diffDays === 1) return "Due tomorrow";
  return `Due in ${diffDays}d`;
}

/** Check if a date is in the past */
export function isOverdue(iso: string | null): boolean {
  if (!iso) return false;
  return new Date(iso) < new Date();
}

/** Format phone as (916) 555-1234 */
export function formatPhone(value: string): string {
  const digits = value.replace(/\D/g, "").slice(0, 10);
  if (digits.length === 0) return "";
  if (digits.length <= 3) return `(${digits}`;
  if (digits.length <= 6) return `(${digits.slice(0, 3)}) ${digits.slice(3)}`;
  return `(${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6)}`;
}

/** Strip phone formatting to digits only */
export function unformatPhone(value: string): string {
  return value.replace(/\D/g, "").slice(0, 10);
}

/** Format number as USD currency */
export function formatCurrency(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
  }).format(value);
}
