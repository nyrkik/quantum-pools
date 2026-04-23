/**
 * @vitest-environment jsdom
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { EmailReplyProposalBody } from "./EmailReplyProposalBody";

const payload = {
  thread_id: "thr-1",
  reply_to_message_id: "msg-1",
  to: "client@example.com",
  subject: "Pump follow-up",
  body: "Thanks for reaching out. We'll take a look and get back to you.",
};

describe("EmailReplyProposalBody", () => {
  it("read mode shows recipient, subject, body", () => {
    render(<EmailReplyProposalBody payload={payload} />);
    expect(screen.getByText(/to client@example.com/i)).toBeInTheDocument();
    expect(screen.getByText("Pump follow-up")).toBeInTheDocument();
    expect(screen.getByText(/Thanks for reaching out/)).toBeInTheDocument();
  });

  it("edit mode exposes editable subject + body", () => {
    render(<EmailReplyProposalBody payload={payload} isEditing onChange={vi.fn()} />);
    expect(screen.getByPlaceholderText("Subject")).toHaveValue("Pump follow-up");
    expect(screen.getByPlaceholderText("Reply body")).toHaveValue(
      "Thanks for reaching out. We'll take a look and get back to you.",
    );
  });

  it("onChange fires with patched payload when body is edited", () => {
    const handle = vi.fn();
    render(<EmailReplyProposalBody payload={payload} isEditing onChange={handle} />);
    fireEvent.change(screen.getByPlaceholderText("Reply body"), {
      target: { value: "Updated body" },
    });
    expect(handle).toHaveBeenCalledWith(
      expect.objectContaining({
        body: "Updated body",
        // Other fields preserved
        subject: "Pump follow-up",
        to: "client@example.com",
      }),
    );
  });
});
