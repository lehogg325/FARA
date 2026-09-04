import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import { useStore } from "../state/store";

const PAGE_SIZE = 25;

function fmtDate(d: string | null): string {
  return d ?? "—";
}

export function RegistrantsBrowseView() {
  const navigate = useStore((s) => s.navigate);
  const back = useStore((s) => s.back);

  const [qInput, setQInput] = useState("");
  const [q, setQ] = useState("");
  const [status, setStatus] = useState<"" | "active" | "terminated">("");
  const [offset, setOffset] = useState(0);

  // Debounce the free-text search so it doesn't fire on every keystroke.
  useEffect(() => {
    const handle = setTimeout(() => { setQ(qInput.trim()); setOffset(0); }, 250);
    return () => clearTimeout(handle);
  }, [qInput]);

  const results = useQuery({
    queryKey: ["registrants-browse", q, status, offset],
    queryFn: () =>
      api.listRegistrants({
        q: q || undefined,
        status: status || undefined,
        offset,
        limit: PAGE_SIZE,
      }),
  });

  const resetPage = <T,>(setter: (v: T) => void) => (v: T) => { setter(v); setOffset(0); };

  return (
    <div>
      <button className="back-link" onClick={back}>&larr; Back</button>

      <div className="record-kicker">Browse</div>
      <h2 className="record-title">Registrants</h2>
      <p className="record-sub" style={{ fontFamily: "var(--serif-body)", fontSize: 14, color: "var(--lunar)" }}>
        Search across every registrant on file — lobbying firms, PR agencies, and individual foreign agents.
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
        <select value={status} onChange={(e) => resetPage(setStatus)(e.target.value as typeof status)}>
          <option value="">Active + terminated</option>
          <option value="active">Active only</option>
          <option value="terminated">Terminated only</option>
        </select>
      </div>

      {results.isLoading && <div className="loading">Loading…</div>}
      {results.isError && <div className="error-state">Could not load results.</div>}
      {results.data && (
        <>
          <div className="row-meta" style={{ marginBottom: 8 }}>{results.data.total.toLocaleString()} registrants</div>
          <ul className="record-list">
            {results.data.items.map((r) => (
              <li key={r.registrant_id}>
                <button
                  className="row-btn"
                  style={{ flexDirection: "column", alignItems: "flex-start", gap: 3 }}
                  onClick={() => navigate({ kind: "registrant", id: r.registrant_id })}
                >
                  <span>
                    {r.name}
                    {r.business_name && <span className="row-meta"> · {r.business_name}</span>}
                  </span>
                  <span className="row-meta">
                    {[r.city, r.state].filter(Boolean).join(", ") || "—"}
                    <span className={`status-pill ${r.status}`} style={{ marginLeft: 6 }}>{r.status}</span>
                    {" · "}registered {fmtDate(r.registration_date)}
                  </span>
                </button>
              </li>
            ))}
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
