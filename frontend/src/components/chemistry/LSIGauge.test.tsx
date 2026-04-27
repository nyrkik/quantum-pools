import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { LSIGauge } from "./LSIGauge";

describe("LSIGauge", () => {
  it("renders the value with sign and 2-decimal precision", () => {
    render(<LSIGauge value={-0.34} classification="corrosive" />);
    expect(screen.getByText("-0.34")).toBeInTheDocument();
  });

  it("renders positive values with explicit + sign", () => {
    render(<LSIGauge value={0.05} classification="balanced" />);
    expect(screen.getByText("+0.05")).toBeInTheDocument();
  });

  it("shows the classification label", () => {
    render(<LSIGauge value={0.6} classification="scaling" />);
    expect(screen.getByText(/scaling/i)).toBeInTheDocument();
  });

  it("renders the caption when supplied", () => {
    render(
      <LSIGauge
        value={0.0}
        classification="balanced"
        caption="temp: 75°F (assumed)"
      />,
    );
    expect(screen.getByText(/temp: 75°F/)).toBeInTheDocument();
  });

  it("sets a useful aria-label for screen readers", () => {
    render(<LSIGauge value={-0.4} classification="corrosive" />);
    const gauge = screen.getByRole("img");
    expect(gauge).toHaveAttribute("aria-label", "LSI -0.40 (corrosive)");
  });

  it("clamps extreme values onto the dial without crashing", () => {
    render(<LSIGauge value={5} classification="scaling" />);
    expect(screen.getByText("+5.00")).toBeInTheDocument();
  });

  it("respects the size prop for the SVG width", () => {
    const { container } = render(
      <LSIGauge value={0} classification="balanced" size={120} />,
    );
    const svg = container.querySelector("svg");
    expect(svg).toHaveAttribute("width", "120");
  });
});
