import { describe, it, expect, vi } from "vitest";
import { render } from "@testing-library/react";

vi.mock("@/lib/api", () => ({ api: { put: vi.fn() } }));
vi.mock("@/lib/events", () => ({ events: { emit: vi.fn() } }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { NextStepRenderer } from "./next-step-registry";

describe("NextStepRenderer", () => {
  it("renders nothing when step is null", () => {
    const { container } = render(<NextStepRenderer step={null} onDone={vi.fn()} />);
    expect(container.firstChild).toBeNull();
  });

  it("logs a warning + renders nothing for an unknown kind", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const { container } = render(
      <NextStepRenderer
        step={{ kind: "invented_kind_from_the_future", initial: {} }}
        onDone={vi.fn()}
      />,
    );
    expect(container.firstChild).toBeNull();
    expect(warn).toHaveBeenCalled();
    warn.mockRestore();
  });

  it("renders the unassigned-pool banner for kind=unassigned_pool", () => {
    const { getByText } = render(
      <NextStepRenderer
        step={{
          kind: "unassigned_pool",
          initial: { entity_type: "job", entity_id: "x", pool_count: 3 },
        }}
        onDone={vi.fn()}
      />,
    );
    expect(getByText(/Added to the unassigned pool/)).toBeInTheDocument();
  });
});
