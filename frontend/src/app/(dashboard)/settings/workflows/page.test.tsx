/**
 * Workflow settings page — happy path + permission gate.
 *
 * Spec: docs/ai-platform-phase-4.md §6.
 * Assertions:
 *  - Loads current config and pre-selects the current handler.
 *  - Clicking a different radio card + Save dispatches PUT with the
 *    new handler name (no enum-prettified value — the UI is
 *    plain-language but the API contract uses the registry key).
 *  - Readonly role (no workflow.manage_config) sees disabled controls
 *    and no Save button.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

const getSpy = vi.fn();
const putSpy = vi.fn();
vi.mock("@/lib/api", () => ({
  api: {
    get: (path: string) => getSpy(path),
    put: (path: string, body: unknown) => putSpy(path, body),
  },
}));

const permsStub = { can: vi.fn((slug: string) => slug === "workflow.manage_config") };
vi.mock("@/lib/permissions", () => ({
  usePermissions: () => permsStub,
}));

vi.mock("@/hooks/use-team-members", () => ({
  useTeamMembersFull: () => [
    { user_id: "u1", first_name: "Kim", last_name: "Nguyen", is_verified: true, is_active: true },
    { user_id: "u2", first_name: "Jose", last_name: "Ramirez", is_verified: true, is_active: true },
  ],
}));

// toast.* calls should not throw in jsdom.
vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

// PageLayout just renders its children — skip the nav chrome in test.
vi.mock("@/components/layout/page-layout", () => ({
  PageLayout: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

import WorkflowSettingsPage from "./page";

describe("WorkflowSettingsPage", () => {
  beforeEach(() => {
    getSpy.mockReset();
    putSpy.mockReset();
    permsStub.can.mockImplementation((slug: string) => slug === "workflow.manage_config");
    getSpy.mockResolvedValue({
      post_creation_handlers: { job: "assign_inline" },
      default_assignee_strategy: { strategy: "last_used_in_org", fallback_user_id: null },
    });
    putSpy.mockResolvedValue({});
  });

  it("loads current config and pre-selects the right radio", async () => {
    render(<WorkflowSettingsPage />);
    await waitFor(() => expect(getSpy).toHaveBeenCalledWith("/v1/workflow/config"));
    const selected = await screen.findByRole("radio", { name: /Create and assign/ });
    expect(selected).toHaveAttribute("aria-checked", "true");
  });

  it("changing handler + Save PUTs the right payload", async () => {
    render(<WorkflowSettingsPage />);
    const scheduleRadio = await screen.findByRole("radio", { name: /Schedule right away/ });
    fireEvent.click(scheduleRadio);
    const saveBtn = await screen.findByRole("button", { name: /Save/ });
    fireEvent.click(saveBtn);
    await waitFor(() => expect(putSpy).toHaveBeenCalledTimes(1));
    expect(putSpy).toHaveBeenCalledWith("/v1/workflow/config", {
      post_creation_handlers: { job: "schedule_inline" },
      default_assignee_strategy: { strategy: "last_used_in_org", fallback_user_id: null },
    });
  });

  it("hides Save button when user lacks workflow.manage_config", async () => {
    permsStub.can.mockImplementation(() => false);
    render(<WorkflowSettingsPage />);
    await waitFor(() => expect(getSpy).toHaveBeenCalled());
    // Even if we try to click another option, Save should not appear because
    // canEdit gates it.
    const scheduleRadio = await screen.findByRole("radio", { name: /Schedule right away/ });
    expect(scheduleRadio).toBeDisabled();
    expect(screen.queryByRole("button", { name: /^Save$/ })).toBeNull();
  });

  it("blocks Save when 'fixed' strategy has no user chosen", async () => {
    render(<WorkflowSettingsPage />);
    const fixedRadio = await screen.findByRole("radio", { name: /Default to a specific person/ });
    fireEvent.click(fixedRadio);
    const saveBtn = await screen.findByRole("button", { name: /Save/ });
    fireEvent.click(saveBtn);
    // No PUT because the guard trips first.
    await new Promise((r) => setTimeout(r, 10));
    expect(putSpy).not.toHaveBeenCalled();
  });
});
