import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";
import "@testing-library/jest-dom/vitest";

// Without `test.globals` in vitest.config.ts, RTL's automatic per-test cleanup
// (which relies on detecting a global afterEach) never registers — do it
// explicitly instead, so one test's rendered DOM doesn't leak into the next.
afterEach(cleanup);
