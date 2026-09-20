import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { api, type SearchResult } from "../api/client";
import { useStore } from "../state/store";

const BADGE_LABEL: Record<SearchResult["entity_type"], string> = {
  registrant: "REGISTRANT",
  foreign_principal: "FOREIGN PRINCIPAL",
  short_form_registrant: "AGENT",
  country: "COUNTRY",
};

export function SearchBox() {
  const [q, setQ] = useState("");
  const [results, setResults] = useState<SearchResult[] | null>(null);
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const navigate = useStore((s) => s.navigate);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    setActiveIndex(-1);
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
    setActiveIndex(-1);
    const grouped = (hit.group_count ?? 1) > 1;
    if (hit.entity_type === "country") navigate({ kind: "country", name: hit.label });
    else if (hit.entity_type === "registrant" && grouped) navigate({ kind: "registrant-group", name: hit.label });
    else if (hit.entity_type === "registrant" && hit.entity_id !== null) navigate({ kind: "registrant", id: hit.entity_id });
    else if (hit.entity_type === "foreign_principal" && grouped) navigate({ kind: "foreign-principal-group", name: hit.label, country: hit.detail });
    else if (hit.entity_type === "foreign_principal" && hit.entity_id !== null) navigate({ kind: "foreign-principal", id: hit.entity_id });
    else if (hit.entity_id !== null) navigate({ kind: "registrant", id: hit.entity_id }); // short-form agents: not their own view yet
  };

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (!open || !results || results.length === 0) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIndex((i) => Math.min(i + 1, results.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      if (activeIndex >= 0) {
        e.preventDefault();
        select(results[activeIndex]);
      }
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  };

  const activeId =
    activeIndex >= 0 && results?.[activeIndex]
      ? `search-hit-${results[activeIndex].entity_type}-${results[activeIndex].entity_id}-${activeIndex}`
      : undefined;

  return (
    <div className="searchbox">
      <input
        type="text"
        placeholder="Search registrants, foreign principals, agents…"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        onKeyDown={onKeyDown}
        role="combobox"
        aria-expanded={open && results !== null}
        aria-controls="search-results-listbox"
        aria-autocomplete="list"
        aria-activedescendant={activeId}
      />
      {open && results !== null && (
        <ul className="search-results" id="search-results-listbox" role="listbox">
          {results.length === 0 ? (
            <li className="search-no-results">No matches</li>
          ) : (
            results.map((r, i) => (
              <li
                key={`${r.entity_type}-${r.entity_id}-${r.label}`}
                id={`search-hit-${r.entity_type}-${r.entity_id}-${i}`}
                role="option"
                aria-selected={i === activeIndex}
                className={i === activeIndex ? "active" : undefined}
                onMouseEnter={() => setActiveIndex(i)}
                onMouseDown={() => select(r)}
              >
                <span className={`badge badge-${r.entity_type}`}>{BADGE_LABEL[r.entity_type]}</span>
                <span className="hit-label">
                  {r.label || "(unnamed)"}
                  {(r.group_count ?? 1) > 1 && (
                    <span className="hit-group-count">
                      {r.entity_type === "registrant"
                        ? `${r.group_count} registrations`
                        : `${r.group_count} registrants`}
                    </span>
                  )}
                </span>
                <span className="hit-meta">
                  {r.detail ? `${r.detail} · ` : ""}
                  {r.registration_number !== null ? `Reg #${r.registration_number}` : ""}
                </span>
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  );
}
