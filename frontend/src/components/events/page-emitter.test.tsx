/**
 * PageEmitter lifecycle tests.
 *
 * Specifically covers the Step-7 audit bug where page.exited was being
 * emitted twice per navigation. The tests mock next/navigation's
 * usePathname and @/lib/events, then exercise mount / re-render /
 * unmount to assert the exact sequence + count of events emitted.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, cleanup } from "@testing-library/react";

// Mock usePathname — Vitest hoists vi.mock so tests can control the return.
let mockPathname = "/";
vi.mock("next/navigation", () => ({
  usePathname: () => mockPathname,
}));

// Mock the events client so we can inspect emissions.
const emitSpy = vi.fn();
vi.mock("@/lib/events", () => ({
  events: {
    emit: (event_type: string, input: unknown) => emitSpy(event_type, input),
  },
}));

// Import AFTER mocks are registered (vitest hoists vi.mock, so order here
// is cosmetic, but explicit post-mock import makes intent clear).
import { PageEmitter } from "./page-emitter";

describe("PageEmitter", () => {
  beforeEach(() => {
    emitSpy.mockReset();
    mockPathname = "/inbox";
  });

  it("emits page.viewed on initial mount", () => {
    render(<PageEmitter />);
    const viewed = emitSpy.mock.calls.filter(([type]) => type === "page.viewed");
    expect(viewed).toHaveLength(1);
    expect(viewed[0][1]).toMatchObject({
      level: "user_action",
      payload: { path: "/inbox", raw_path: "/inbox" },
    });
  });

  it("does NOT emit page.exited on initial mount", () => {
    render(<PageEmitter />);
    const exited = emitSpy.mock.calls.filter(([type]) => type === "page.exited");
    expect(exited).toHaveLength(0);
  });

  it("normalizes UUID path segments to [id] template", () => {
    mockPathname = "/customers/11111111-2222-3333-4444-555555555555";
    render(<PageEmitter />);
    const viewed = emitSpy.mock.calls.find(([type]) => type === "page.viewed");
    expect(viewed![1]).toMatchObject({
      payload: {
        path: "/customers/[id]",
        raw_path: "/customers/11111111-2222-3333-4444-555555555555",
      },
    });
  });

  it("emits page.exited exactly once on unmount from a dwell-tracked page", () => {
    const { unmount } = render(<PageEmitter />);
    emitSpy.mockClear();
    unmount();
    const exited = emitSpy.mock.calls.filter(([type]) => type === "page.exited");
    expect(exited).toHaveLength(1);
    expect(exited[0][1]).toMatchObject({
      level: "user_action",
      payload: { path: "/inbox", raw_path: "/inbox" },
    });
    // dwell_ms should be a non-negative integer
    const dwell = (exited[0][1] as { payload: { dwell_ms: number } }).payload.dwell_ms;
    expect(typeof dwell).toBe("number");
    expect(dwell).toBeGreaterThanOrEqual(0);
  });

  it("does NOT emit page.exited on unmount from a non-dwell-tracked page", () => {
    // /login is not in DWELL_TRACKED_PREFIXES
    mockPathname = "/login";
    const { unmount } = render(<PageEmitter />);
    emitSpy.mockClear();
    unmount();
    expect(emitSpy.mock.calls.filter(([type]) => type === "page.exited")).toHaveLength(0);
  });

  it("emits page.exited ONCE and page.viewed ONCE on route change — THE double-emit regression guard", () => {
    // This is the exact regression from the Step 7 audit. If either fires
    // twice, the analytics pipeline sees bad data.
    const { rerender } = render(<PageEmitter />);
    emitSpy.mockClear();

    // Navigate from /inbox to /cases/<uuid>
    const uuid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee";
    mockPathname = `/cases/${uuid}`;
    rerender(<PageEmitter />);

    const exited = emitSpy.mock.calls.filter(([type]) => type === "page.exited");
    const viewed = emitSpy.mock.calls.filter(([type]) => type === "page.viewed");

    expect(exited).toHaveLength(1);
    expect(exited[0][1]).toMatchObject({
      payload: { path: "/inbox", raw_path: "/inbox" },
    });

    expect(viewed).toHaveLength(1);
    expect(viewed[0][1]).toMatchObject({
      payload: { path: "/cases/[id]", raw_path: `/cases/${uuid}` },
    });
  });

  it("does not treat /settings-export as a /settings page (prefix boundary)", () => {
    // Regression for the prefix-match audit fix.
    mockPathname = "/settings-export";
    const { unmount } = render(<PageEmitter />);
    emitSpy.mockClear();
    unmount();
    // Should NOT fire page.exited because /settings-export isn't actually
    // a dwell-tracked surface.
    expect(emitSpy.mock.calls.filter(([type]) => type === "page.exited")).toHaveLength(0);
  });

  it("correctly tracks /settings (exact match) as dwell-tracked", () => {
    mockPathname = "/settings";
    const { unmount } = render(<PageEmitter />);
    emitSpy.mockClear();
    unmount();
    expect(emitSpy.mock.calls.filter(([type]) => type === "page.exited")).toHaveLength(1);
  });

  it("correctly tracks /settings/notifications (child) as dwell-tracked", () => {
    mockPathname = "/settings/notifications";
    const { unmount } = render(<PageEmitter />);
    emitSpy.mockClear();
    unmount();
    expect(emitSpy.mock.calls.filter(([type]) => type === "page.exited")).toHaveLength(1);
  });

  it("renders null (no DOM output)", () => {
    const { container } = render(<PageEmitter />);
    expect(container.firstChild).toBeNull();
    cleanup();
  });
});
