import { beforeEach, describe, expect, it } from "vitest";
import { useStore } from "./store";

beforeEach(() => {
  window.history.replaceState(null, "", "/");
  useStore.setState({ view: { kind: "home" } });
});

function waitForPopstate(): Promise<void> {
  return new Promise((resolve) => window.addEventListener("popstate", () => resolve(), { once: true }));
}

describe("useStore navigate/back", () => {
  it("navigate() pushes a real URL and updates view", () => {
    useStore.getState().navigate({ kind: "registrant", id: 540 });
    expect(window.location.pathname).toBe("/registrants/540");
    expect(useStore.getState().view).toEqual({ kind: "registrant", id: 540 });
  });

  it("back() steps to the immediately preceding view via the browser's own history, not straight to the start", async () => {
    useStore.getState().navigate({ kind: "registrants-browse" });
    useStore.getState().navigate({ kind: "registrant", id: 540 });
    useStore.getState().navigate({ kind: "foreign-principal", id: 7 });

    useStore.getState().back();
    await waitForPopstate();
    expect(useStore.getState().view).toEqual({ kind: "registrant", id: 540 });

    useStore.getState().back();
    await waitForPopstate();
    expect(useStore.getState().view).toEqual({ kind: "registrants-browse" });
  });

  it("does not push a duplicate history entry for a navigation that resolves to the same URL", async () => {
    // Mirrors the guided tour's two consecutive steps that both land on
    // CHINA's Overview tab -- clicking "Next" between them shouldn't leave a
    // redundant entry a user has to click back twice to get past.
    useStore.getState().navigate({ kind: "country", name: "CHINA", tab: "overview" });
    useStore.getState().navigate({ kind: "country", name: "CHINA", tab: "overview" });
    useStore.getState().navigate({ kind: "country", name: "CHINA", tab: "network" });

    useStore.getState().back();
    await waitForPopstate();
    // One back() from the network tab lands on the (deduped, single-entry)
    // Overview view -- not skipping past it, just not double-counting it.
    expect(useStore.getState().view).toEqual({ kind: "country", name: "CHINA", tab: undefined });

    useStore.getState().back();
    await waitForPopstate();
    expect(useStore.getState().view).toEqual({ kind: "home" });
  });
});
