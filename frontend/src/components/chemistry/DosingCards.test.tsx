import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { DosingCards, type DosingRecord } from "./DosingCards";

const okRow: DosingRecord = {
  parameter: "pH",
  current: 7.4,
  target: "7.2 – 7.6",
  status: "ok",
  chemical: null,
  amount: null,
};

const lowRow: DosingRecord = {
  parameter: "Free Chlorine",
  current: 0.5,
  target: "1 – 5 ppm",
  status: "low",
  chemical: "Liquid chlorine (12.5%)",
  amount: "25 oz",
  notes: "Add along the deep end with pump running.",
};

const highRow: DosingRecord = {
  parameter: "pH",
  current: 8.2,
  target: "7.2 – 7.6",
  status: "high",
  chemical: "Muriatic acid (31.45%)",
  amount: "16 oz",
  notes: "Pour into deep end with pump running. Never near skimmer.",
};


describe("DosingCards", () => {
  it("renders nothing when recommendations are empty", () => {
    const { container } = render(<DosingCards recommendations={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders nothing when recommendations are null", () => {
    const { container } = render(<DosingCards recommendations={null} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders an OK card without chemical or notes", () => {
    render(<DosingCards recommendations={[okRow]} />);
    expect(screen.getByText("pH")).toBeInTheDocument();
    expect(screen.getByText("OK")).toBeInTheDocument();
    expect(screen.getByText(/Target:/)).toBeInTheDocument();
    // No chemical/amount line for OK rows
    expect(screen.queryByText(/Soda ash|Liquid chlorine|Muriatic/)).toBeNull();
  });

  it("renders chemical + amount + notes for a low status", () => {
    render(<DosingCards recommendations={[lowRow]} />);
    expect(screen.getByText("Free Chlorine")).toBeInTheDocument();
    expect(screen.getByText("low")).toBeInTheDocument();
    expect(screen.getByText("Liquid chlorine (12.5%)")).toBeInTheDocument();
    expect(screen.getByText(/25 oz/)).toBeInTheDocument();
    expect(screen.getByText(/deep end/)).toBeInTheDocument();
  });

  it("renders all three states stacked", () => {
    render(<DosingCards recommendations={[okRow, lowRow, highRow]} />);
    expect(screen.getByText("Free Chlorine")).toBeInTheDocument();
    expect(screen.getByText("Muriatic acid (31.45%)")).toBeInTheDocument();
    // OK + low + high (note pH appears twice — once OK, once high)
    expect(screen.getAllByText(/pH/)).toHaveLength(2);
  });
});
