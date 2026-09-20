import { create } from "zustand";
import { pathToView, viewToPath } from "./url";

export type View =
  | { kind: "home" }
  | { kind: "registrant"; id: number }
  | { kind: "registrant-group"; name: string }
  | { kind: "foreign-principal"; id: number }
  | { kind: "foreign-principal-group"; name: string; country: string | null }
  | { kind: "document"; id: number }
  | { kind: "document-search"; q: string }
  | { kind: "country"; name: string; tab?: "overview" | "network" | "topics" }
  | { kind: "foreign-principals-browse" }
  | { kind: "registrants-browse" }
  | { kind: "documents-browse" };

interface Store {
  view: View;
  navigate: (v: View) => void;
  back: () => void;
}

// The browser's own session history is the single source of truth for
// "back" — no separate in-memory stack to keep in sync with it. navigate()
// pushes a real URL per view (mirrored back by pathToView/viewToPath), so
// the native back/forward buttons retrace exactly what the user clicked
// through, and a refresh or shared link lands on the right view instead of
// always resetting to home.
export const useStore = create<Store>((set) => ({
  view: pathToView(window.location.pathname, window.location.search),
  navigate: (v) => {
    const path = viewToPath(v);
    if (window.location.pathname + window.location.search !== path) {
      window.history.pushState(null, "", path);
    }
    set({ view: v });
  },
  back: () => window.history.back(),
}));

// history.back()/forward() are asynchronous — the browser fires popstate once
// the navigation actually happens, which is when `view` should update.
window.addEventListener("popstate", () => {
  useStore.setState({ view: pathToView(window.location.pathname, window.location.search) });
});
