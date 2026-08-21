import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach } from "vitest";

import { resetBrowserState } from "@/test/browser-mocks";

beforeEach(resetBrowserState);

afterEach(() => {
  cleanup();
  resetBrowserState();
});
