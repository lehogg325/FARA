import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api/client";
import { useStore } from "../state/store";

const PAGE_SIZE = 25;

function fmtDate(d: string | null): string {
  return d ?? "—";
}

export function DocumentsBrowseView() {
  const navigate = useStore((s) => s.navigate);
  const back = useStore((s) => s.back);

  const [documentType, setDocumentType] = useState("");
  const [country, setCountry] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [offset, setOffset] = useState(0);

  const documentTypes = useQuery({ queryKey: ["document-types"], queryFn: api.documentTypes, staleTime: Infinity });
  const countries = useQuery({ queryKey: ["countries"], queryFn: api.countries, staleTime: Infinity });
  const results = useQuery({
    queryKey: ["documents-browse", documentType, country, dateFrom, dateTo, offset],
    queryFn: () =>
      api.listDocuments({
        document_type: documentType || undefined,
        country: country || undefined,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
        offset,
        limit: PAGE_SIZE,
      }),
  });

  const resetPage = <T,>(setter: (v: T) => void) => (v: T) => { setter(v); setOffset(0); };

  return (
    <div>
      <button className="back-link" onClick={back}>&larr; Back</button>

      <div className="record-kicker">Browse</div>
      <h2 className="record-title">Filings</h2>
      <p className="record-sub" style={{ fontFamily: "var(--serif-body)", fontSize: 14, color: "var(--lunar)" }}>
        Every document on file, filterable by type, country, and date. For full-text search across filing
        language, use "Search text" on the home page instead.
      </p>

      <div style={{ display: "flex", flexWrap: "wrap", gap: 10, margin: "18px 0" }}>
        <select value={documentType} onChange={(e) => resetPage(setDocumentType)(e.target.value)}>
          <option value="">All document types</option>
          {(documentTypes.data ?? []).map((t) => (
            <option key={t.document_type_code} value={t.document_type_code}>{t.document_type_label}</option>
          ))}
        </select>
        <select value={country} onChange={(e) => resetPage(setCountry)(e.target.value)}>
          <option value="">All countries</option>
          {(countries.data ?? []).map((c) => (
            <option key={c.country_name} value={c.country_name}>
              {c.note ? `${c.country_name} — ${c.note}` : c.country_name}
            </option>
          ))}
        </select>
        <input
          type="date"
          value={dateFrom}
          onChange={(e) => resetPage(setDateFrom)(e.target.value)}
          title="Filed on or after"
          style={{
            padding: "8px 10px", fontFamily: "var(--mono)", fontSize: 12,
            color: "var(--lunar)", background: "var(--panel)", border: "1px solid var(--rule)", borderRadius: 4,
          }}
        />
        <input
          type="date"
          value={dateTo}
          onChange={(e) => resetPage(setDateTo)(e.target.value)}
          title="Filed on or before"
          style={{
            padding: "8px 10px", fontFamily: "var(--mono)", fontSize: 12,
            color: "var(--lunar)", background: "var(--panel)", border: "1px solid var(--rule)", borderRadius: 4,
          }}
        />
      </div>

      {results.isLoading && <div className="loading">Loading…</div>}
      {results.isError && <div className="error-state">Could not load results.</div>}
      {results.data && (
        <>
          <div className="row-meta" style={{ marginBottom: 8 }}>{results.data.total.toLocaleString()} filings</div>
          <ul className="record-list">
            {results.data.items.map((d) => (
              <li key={d.registrant_doc_id}>
                <button
                  className="row-btn"
                  style={{ flexDirection: "column", alignItems: "flex-start", gap: 3 }}
                  onClick={() => navigate({ kind: "document", id: d.registrant_doc_id })}
                >
                  <span>
                    {d.document_type_raw_label}
                    {d.short_form_name && <span className="row-meta"> · {d.short_form_name}</span>}
                  </span>
                  <span className="row-meta">
                    {d.foreign_principal_name && `${d.foreign_principal_name} · `}
                    {d.foreign_principal_country_raw && `${d.foreign_principal_country_raw} · `}
                    filed {fmtDate(d.date_stamped)}
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
