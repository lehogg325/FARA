import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api/client";
import { useStore } from "../state/store";

export function EmptyState() {
  const meta = useQuery({ queryKey: ["meta"], queryFn: api.meta, staleTime: Infinity });
  const countries = useQuery({ queryKey: ["countries"], queryFn: api.countries, staleTime: Infinity });
  const navigate = useStore((s) => s.navigate);
  const [textQuery, setTextQuery] = useState("");
  const topCountries = (countries.data ?? []).filter((c) => c.registrant_count > 0).slice(0, 12);

  return (
    <div className="empty-state">
      <p>
        Every foreign agent registered under the Foreign Agents Registration Act files
        disclosures with the Department of Justice — who they represent, what they're
        paid, and what political activity they conduct on a foreign principal's behalf.
        Search for any registrant, foreign principal, or registered agent above, or
        search the full text of every filing below.
      </p>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (textQuery.trim()) navigate({ kind: "document-search", q: textQuery.trim() });
        }}
        className="text-search-form"
      >
        <input
          type="text"
          value={textQuery}
          onChange={(e) => setTextQuery(e.target.value)}
          placeholder="Search filing text, e.g. lobbying strategy…"
        />
        <button type="submit" className="btn-primary">Search text</button>
      </form>

      {topCountries.length > 0 && (
        <div className="meta-strip">
          <div className="meta-strip-title">Browse by country</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {topCountries.map((c) => (
              <button
                key={c.country_name}
                className="back-link"
                style={{
                  border: "1px solid var(--rule)", borderRadius: 3, padding: "6px 10px",
                  color: "var(--lunar)", fontFamily: "var(--serif-body)", fontSize: 13,
                }}
                onClick={() => navigate({ kind: "country", name: c.country_name })}
              >
                {c.country_name} <span className="row-meta">({c.registrant_count})</span>
              </button>
            ))}
          </div>
        </div>
      )}

      {meta.data && (
        <div className="meta-strip">
          <div className="meta-strip-title">Coverage</div>
          {meta.data.datasets.map((d) => (
            <div className="meta-row" key={d.dataset}>
              <span className="label">{d.dataset.replace(/_/g, " ")}</span>
              <span className="value">{d.loaded_row_count.toLocaleString()}</span>
            </div>
          ))}
          {meta.data.extraction_coverage.map((c) => (
            <div className="meta-row" key={c.stage}>
              <span className="label">{c.stage.replace(/_/g, " ")} extracted</span>
              <span className="value">
                {c.succeeded_count.toLocaleString()} / {c.eligible_count.toLocaleString()}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
