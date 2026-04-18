/**
 * Vitest setup — runs once per test file before any test executes.
 *
 * Installs @testing-library/jest-dom matchers (e.g., toBeInTheDocument)
 * onto expect globally, so every test can assert against the DOM without
 * re-importing.
 */

import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

// Unmount any components mounted during a test so DOM state doesn't leak
// into the next test.
afterEach(() => {
  cleanup();
});
