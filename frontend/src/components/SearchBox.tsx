import { useEffect, useRef, useState } from "react";
import { api, type SearchResult } from "../api/client";
import { useStore } from "../state/store";

const BADGE_LABEL: Record<SearchResult["entity_type"], string> = {
  registrant: "REGISTRANT",
  foreign_principal: "FOREIGN PRINCIPAL",
  short_form_registrant: "AGENT",
};

export function SearchBox() {
  const [q, setQ] = useState("");
  const [results, setResults] = useState<SearchResult[] | null>(null);
  const [open, setOpen] = useState(false);
  const navigate = useStore((s) => s.navigate);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (q.trim().length < 2) {
      setResults(null);
      return;
    }
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const handle = setTimeout(() => {
      api
        .search(q.trim(), undefined, controller.signal)
        .then(setResults)
        .catch((e) => {
          if (e.name !== "AbortError") setResults([]);
        });
    }, 200);
    return () => clearTimeout(handle);
  }, [q]);

  const select = (hit: SearchResult) => {
    setOpen(false);
    setQ("");
    setResults(null);
    if (hit.entity_type === "registrant") navigate({ kind: "registrant", id: hit.entity_id });
    else if (hit.entity_type === "foreign_principal") navigate({ kind: "foreign-principal", id: hit.entity_id });
    else navigate({ kind: "registrant", id: hit.entity_id }); // short-form agents: not their own view yet
  };

  return (
    <div className="searchbox">
      <input
        type="text"
        placeholder="Search registrants, foreign principals, agents…"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
      />
      {open && results !== null && (
        <ul className="search-results">
          {results.length === 0 ? (
            <li className="search-no-results">No matches</li>
          ) : (
            results.map((r) => (
              <li key={`${r.entity_type}-${r.entity_id}`} onClick={() => select(r)}>
                <span className={`badge badge-${r.entity_type}`}>{BADGE_LABEL[r.entity_type]}</span>
                <span className="hit-label">{r.label || "(unnamed)"}</span>
                <span className="hit-meta">
                  {r.detail ? `${r.detail} · ` : ""}Reg #{r.registration_number}
                </span>
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  );
}
