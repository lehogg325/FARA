import { create } from "zustand";

export type View =
  | { kind: "home" }
  | { kind: "registrant"; id: number }
  | { kind: "foreign-principal"; id: number }
  | { kind: "foreign-principal-group"; name: string; country: string | null }
  | { kind: "document"; id: number }
  | { kind: "document-search"; q: string }
  | { kind: "country"; name: string };

interface Store {
  view: View;
  history: View[];
  navigate: (v: View) => void;
  back: () => void;
}

export const useStore = create<Store>((set, get) => ({
  view: { kind: "home" },
  history: [],
  navigate: (v) => set((s) => ({ view: v, history: [...s.history, s.view] })),
  back: () => {
    const h = [...get().history];
    const prev = h.pop();
    set({ view: prev ?? { kind: "home" }, history: h });
  },
}));
