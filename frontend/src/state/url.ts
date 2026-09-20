// Maps View <-> real URLs, mirroring the backend's own REST paths minus the
// /api prefix (/registrants/:id, /foreign-principals/:id, etc.). This is what
// lets the browser's native back/forward actually retrace the app's
// navigation instead of just resetting to home on every "back" — see
// state/store.ts, which pushes one of these paths per navigate() call.
import type { View } from "./store";

export function viewToPath(view: View): string {
  switch (view.kind) {
    case "home":
      return "/";
    case "registrants-browse":
      return "/registrants";
    case "registrant":
      return `/registrants/${view.id}`;
    case "registrant-group":
      return `/registrants/by-name/${encodeURIComponent(view.name)}`;
    case "foreign-principals-browse":
      return "/foreign-principals";
    case "foreign-principal":
      return `/foreign-principals/${view.id}`;
    case "foreign-principal-group": {
      const qs = view.country ? `?country=${encodeURIComponent(view.country)}` : "";
      return `/foreign-principals/by-name/${encodeURIComponent(view.name)}${qs}`;
    }
    case "documents-browse":
      return "/documents";
    case "document":
      return `/documents/${view.id}`;
    case "document-search":
      return `/documents/search?q=${encodeURIComponent(view.q)}`;
    case "country": {
      const qs = view.tab && view.tab !== "overview" ? `?tab=${view.tab}` : "";
      return `/countries/${encodeURIComponent(view.name)}${qs}`;
    }
  }
}

export function pathToView(pathname: string, search: string): View {
  const params = new URLSearchParams(search);
  const parts = pathname.split("/").filter(Boolean).map(decodeURIComponent);

  if (parts.length === 0) return { kind: "home" };

  if (parts[0] === "registrants") {
    if (parts.length === 1) return { kind: "registrants-browse" };
    if (parts[1] === "by-name" && parts[2]) return { kind: "registrant-group", name: parts[2] };
    const id = Number(parts[1]);
    if (Number.isInteger(id)) return { kind: "registrant", id };
  } else if (parts[0] === "foreign-principals") {
    if (parts.length === 1) return { kind: "foreign-principals-browse" };
    if (parts[1] === "by-name" && parts[2]) {
      return { kind: "foreign-principal-group", name: parts[2], country: params.get("country") };
    }
    const id = Number(parts[1]);
    if (Number.isInteger(id)) return { kind: "foreign-principal", id };
  } else if (parts[0] === "documents") {
    if (parts.length === 1) return { kind: "documents-browse" };
    if (parts[1] === "search") return { kind: "document-search", q: params.get("q") ?? "" };
    const id = Number(parts[1]);
    if (Number.isInteger(id)) return { kind: "document", id };
  } else if (parts[0] === "countries" && parts[1]) {
    const tab = params.get("tab");
    return {
      kind: "country",
      name: parts[1],
      tab: tab === "network" || tab === "topics" || tab === "overview" ? tab : undefined,
    };
  }

  return { kind: "home" };
}
