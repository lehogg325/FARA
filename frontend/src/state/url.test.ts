import { describe, expect, it } from "vitest";
import type { View } from "./store";
import { pathToView, viewToPath } from "./url";

const CASES: View[] = [
  { kind: "home" },
  { kind: "registrants-browse" },
  { kind: "registrant", id: 540 },
  { kind: "registrant-group", name: "Brownstein Hyatt Farber Schreck, LLP" },
  { kind: "foreign-principals-browse" },
  { kind: "foreign-principal", id: 123 },
  { kind: "foreign-principal-group", name: "Ministry of Foreign Affairs", country: "JAPAN" },
  { kind: "foreign-principal-group", name: "Some Principal", country: null },
  { kind: "documents-browse" },
  { kind: "document", id: 456 },
  { kind: "document-search", q: "lobbying strategy" },
  { kind: "country", name: "JAPAN" },
  { kind: "country", name: "KOREA, NORTH", tab: "network" },
  { kind: "country", name: "CHINA", tab: "topics" },
  { kind: "country", name: "CHINA", tab: "overview" },
];

describe("viewToPath / pathToView round-trip", () => {
  for (const view of CASES) {
    it(`round-trips ${JSON.stringify(view)}`, () => {
      const path = viewToPath(view);
      const url = new URL(path, "http://localhost");
      const parsed = pathToView(url.pathname, url.search);
      // "overview" is the implicit default and never gets written into the
      // URL, so it round-trips as undefined -- both mean the same tab to Tabs.
      const expected = view.kind === "country" && view.tab === "overview" ? { ...view, tab: undefined } : view;
      expect(parsed).toEqual(expected);
    });
  }
});

describe("pathToView edge cases", () => {
  it("falls back to home for an unrecognized path", () => {
    expect(pathToView("/nonsense/path/here", "")).toEqual({ kind: "home" });
  });

  it("falls back to home for a non-numeric id", () => {
    expect(pathToView("/registrants/not-a-number", "")).toEqual({ kind: "home" });
  });

  it("defaults foreign-principal-group country to null when the query param is absent", () => {
    expect(pathToView("/foreign-principals/by-name/Acme", "")).toEqual({
      kind: "foreign-principal-group",
      name: "Acme",
      country: null,
    });
  });
});
