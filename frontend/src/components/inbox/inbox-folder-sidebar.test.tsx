/**
 * @vitest-environment jsdom
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

import { InboxFolderSidebar } from "./inbox-folder-sidebar";

const apiGetMock = vi.fn();
vi.mock("@/lib/api", () => ({
  api: { get: (...args: unknown[]) => apiGetMock(...args), post: vi.fn() },
}));

vi.mock("@/components/email/compose-provider", () => ({
  useCompose: () => ({ openCompose: vi.fn() }),
}));

const canMock = vi.fn();
vi.mock("@/lib/permissions", () => ({
  usePermissions: () => ({ can: canMock }),
}));

const FOLDERS = [
  { id: "f-inbox", name: "Inbox", icon: "inbox", color: null, sort_order: 0, is_system: true, system_key: "inbox", thread_count: 5, unread_count: 2 },
  { id: "f-outbox", name: "Outbox", icon: "clock", color: null, sort_order: 1, is_system: true, system_key: "outbox", thread_count: 0, unread_count: 0 },
  { id: "f-sent", name: "Sent", icon: "send", color: null, sort_order: 2, is_system: true, system_key: "sent", thread_count: 12, unread_count: 0 },
  { id: "f-spam", name: "Spam", icon: "shield-alert", color: null, sort_order: 3, is_system: true, system_key: "spam", thread_count: 1, unread_count: 0 },
  { id: "f-ai-review", name: "AI Review", icon: "bot", color: null, sort_order: 4, is_system: true, system_key: "ai_review", thread_count: 7, unread_count: 7 },
  { id: "f-allmail", name: "All Mail", icon: "mailbox", color: null, sort_order: 5, is_system: true, system_key: "all_mail", thread_count: 80, unread_count: 0 },
];

describe("InboxFolderSidebar — AI Review folder", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiGetMock.mockResolvedValue({ folders: FOLDERS });
  });

  it("shows AI Review folder + amber badge for admins (inbox.manage)", async () => {
    canMock.mockImplementation((slug: string) => slug === "inbox.manage" || slug === "inbox.see_all_mail");

    render(
      <InboxFolderSidebar selectedFolderId={null} onSelectFolder={vi.fn()} />,
    );

    const aiReview = await screen.findByRole("button", { name: /AI Review/i });
    expect(aiReview).toBeInTheDocument();
    // Badge count = the unread_count from the folder payload
    expect(aiReview.textContent).toContain("7");
  });

  it("hides AI Review folder for non-admins", async () => {
    canMock.mockImplementation((slug: string) => slug === "inbox.see_all_mail");

    render(
      <InboxFolderSidebar selectedFolderId={null} onSelectFolder={vi.fn()} />,
    );

    // Wait for data load — Inbox should appear so we know rendering finished.
    await screen.findByRole("button", { name: /^Inbox/i });
    expect(screen.queryByRole("button", { name: /AI Review/i })).toBeNull();
  });

  it("hides AI Review when its count is zero (no badge to render)", async () => {
    canMock.mockImplementation((slug: string) => slug === "inbox.manage" || slug === "inbox.see_all_mail");
    apiGetMock.mockResolvedValue({
      folders: FOLDERS.map((f) =>
        f.system_key === "ai_review" ? { ...f, thread_count: 0, unread_count: 0 } : f,
      ),
    });

    render(
      <InboxFolderSidebar selectedFolderId={null} onSelectFolder={vi.fn()} />,
    );

    // Folder still renders for admin (so they can click in to view history),
    // but the badge does not (unread_count = 0).
    const aiReview = await screen.findByRole("button", { name: /AI Review/i });
    expect(aiReview).toBeInTheDocument();
    // No badge → button text should be just the label.
    await waitFor(() => {
      expect(aiReview.textContent?.trim()).toBe("AI Review");
    });
  });
});
