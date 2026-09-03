import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api, type ForeignPrincipal, type ForeignPrincipalGrouped, type ForeignPrincipalSort } from "../api/client";
import { useStore } from "../state/store";

const PAGE_SIZE = 25;

function fmtDate(d: string | null): string {
  return d ?? "—";
}

function isGrouped(item: ForeignPrincipal | ForeignPrincipalGrouped): item is ForeignPrincipalGrouped {
  return "registrant_count" in item;
}

export function ForeignPrincipalsBrowseView() {
  const navigate = useStore((s) => s.navigate);
  const back = useStore((s) => s.back);

  const [qInput, setQInput] = useState("");
  const [q, setQ] = useState("");
  const [country, setCountry] = useState("");
  const [status, setStatus] = useState<"" | "active" | "terminated">("");
  const [sort, setSort] = useState<ForeignPrincipalSort>("registration_date_desc");
  const [groupByName, setGroupByName] = useState(true);
  const [offset, setOffset] = useState(0);

  // Debounce the free-text search so it doesn't fire on every keystroke.
  useEffect(() => {
    const handle = setTimeout(() => { setQ(qInput.trim()); setOffset(0); }, 250);
    return () => clearTimeout(handle);
  }, [qInput]);

  const countries = useQuery({ queryKey: ["countries"], queryFn: api.countries, staleTime: Infinity });
  const results = useQuery({
    queryKey: ["fp-browse", q, country, status, sort, groupByName, offset],
    queryFn: () =>
      api.searchForeignPrincipals({
        q: q || undefined,
        country: country || undefined,
        status: status || undefined,
        sort,
        group_by_name: groupByName,
        offset,
        limit: PAGE_SIZE,
      }),
  });

  const resetPage = <T,>(setter: (v: T) => void) => (v: T) => { setter(v); setOffset(0); };

  return (
    <div>
      <button className="back-link" onClick={back}>&larr; Back</button>

      <div className="record-kicker">Browse</div>
      <h2 className="record-title">Foreign Principals</h2>
      <p className="record-sub" style={{ fontFamily: "var(--serif-body)", fontSize: 14, color: "var(--lunar)" }}>
        Search across every foreign principal on file directly — no need to find their registrant first.
      </p>

      <div style={{ display: "flex", flexWrap: "wrap", gap: 10, margin: "18px 0" }}>
        <input
          type="text"
          value={qInput}
          onChange={(e) => setQInput(e.target.value)}
          placeholder="Search by name…"
          style={{
            flex: "1 1 240px", padding: "9px 13px", fontFamily: "var(--mono)", fontSize: 13,
            color: "var(--lunar)", background: "var(--panel)", border: "1px solid var(--rule)", borderRadius: 4,
          }}
        />
        <select value={country} onChange={(e) => resetPage(setCountry)(e.target.value)}>
          <option value="">All countries</option>
          {(countries.data ?? []).map((c) => (
            <option key={c.country_name} value={c.country_name}>
              {c.note ? `${c.country_name} — ${c.note}` : c.country_name}
            </option>
          ))}
        </select>
        <select value={status} onChange={(e) => resetPage(setStatus)(e.target.value as typeof status)}>
          <option value="">Active + terminated registrants</option>
          <option value="active">Active registrants only</option>
          <option value="terminated">Terminated registrants only</option>
        </select>
        <select value={sort} onChange={(e) => resetPage(setSort)(e.target.value as ForeignPrincipalSort)}>
          <option value="registration_date_desc">Newest first</option>
          <option value="name_asc">Name (A–Z)</option>
          <option value="country_asc">Country (A–Z)</option>
        </select>
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={groupByName}
            onChange={(e) => resetPage(setGroupByName)(e.target.checked)}
          />
          Group by principal name
        </label>
      </div>

      {results.isLoading && <div className="loading">Loading…</div>}
      {results.isError && <div className="error-state">Could not load results.</div>}
      {results.data && (
        <>
          <div className="row-meta" style={{ marginBottom: 8 }}>{results.data.total.toLocaleString()} foreign principals</div>
          <ul className="record-list">
            {results.data.items.map((fp) =>
              isGrouped(fp) ? (
                <li key={`${fp.foreign_principal_name}-${fp.country_raw}`}>
                  <button
                    className="row-btn"
                    style={{ flexDirection: "column", alignItems: "flex-start", gap: 3 }}
                    onClick={() => navigate({ kind: "foreign-principal-group", name: fp.foreign_principal_name, country: fp.country_raw })}
                  >
                    <span>
                      {fp.foreign_principal_name}
                      {fp.country_raw && <span className="row-meta"> · {fp.country_raw}</span>}
                    </span>
                    <span className="row-meta">
                      {fp.registrant_count} registrant{fp.registrant_count === 1 ? "" : "s"}: {fp.sample_registrant_names.join(", ")}
                      {fp.registrant_count > fp.sample_registrant_names.length ? "…" : ""}
                      {" · "}latest {fmtDate(fp.latest_registration_date)}
                    </span>
                  </button>
                </li>
              ) : (
                <li key={fp.foreign_principal_id}>
                  <button
                    className="row-btn"
                    style={{ flexDirection: "column", alignItems: "flex-start", gap: 3 }}
                    onClick={() => navigate({ kind: "foreign-principal", id: fp.foreign_principal_id })}
                  >
                    <span>
                      {fp.foreign_principal_name}
                      {fp.country_raw && <span className="row-meta"> · {fp.country_raw}</span>}
                    </span>
                    <span className="row-meta">
                      represented by {fp.registrant_name}
                      <span className={`status-pill ${fp.registrant_status}`} style={{ marginLeft: 6 }}>{fp.registrant_status}</span>
                      {" · "}registered {fmtDate(fp.registration_date)}
                    </span>
                  </button>
                </li>
              ),
            )}
            {results.data.items.length === 0 && <li className="loading">No matches.</li>}
          </ul>
          {results.data.total > PAGE_SIZE && (
            <div className="pagination">
              <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>&larr; Prev</button>
              <span className="row-meta">{offset + 1}–{Math.min(offset + PAGE_SIZE, results.data.total)} of {results.data.total}</span>
              <button disabled={offset + PAGE_SIZE >= results.data.total} onClick={() => setOffset(offset + PAGE_SIZE)}>Next &rarr;</button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
