import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api/client";
import { useStore } from "../state/store";

const PAGE_SIZE = 15;

// The backend's ts_headline() wraps matched terms in <b>...</b> — but the
// surrounding text comes from OCR'd/extracted PDF content we don't fully
// trust, so this splits on that fixed marker and renders each part as plain
// React text (auto-escaped) instead of via dangerouslySetInnerHTML, which
// would execute any stray "<" sequence a filing's extracted text happened to
// contain.
function renderSnippet(snippet: string): React.ReactNode {
  const parts = snippet.split(/(<b>|<\/b>)/);
  const nodes: React.ReactNode[] = [];
  let bold = false;
  parts.forEach((part, i) => {
    if (part === "<b>") { bold = true; return; }
    if (part === "</b>") { bold = false; return; }
    nodes.push(bold ? <strong key={i}>{part}</strong> : part);
  });
  return nodes;
}

export function DocumentSearchView({ q }: { q: string }) {
  const navigate = useStore((s) => s.navigate);
  const back = useStore((s) => s.back);
  const [offset, setOffset] = useState(0);

  const results = useQuery({
    queryKey: ["doc-search", q, offset],
    queryFn: () => api.documentSearch(q, offset, PAGE_SIZE),
  });

  return (
    <div>
      <button className="back-link" onClick={back}>&larr; Back</button>

      <div className="record-kicker">Full-text filing search</div>
      <h2 className="record-title">"{q}"</h2>

      {results.isLoading && <div className="loading">Searching…</div>}
      {results.data && (
        <>
          <div className="record-sub">{results.data.total.toLocaleString()} matching filings</div>
          <ul className="record-list">
            {results.data.items.map((r) => (
              <li key={r.registrant_doc_id}>
                <button className="row-btn" style={{ flexDirection: "column", alignItems: "flex-start", gap: 4 }}
                  onClick={() => navigate({ kind: "document", id: r.registrant_doc_id })}>
                  <span>
                    {r.document_type_raw_label} · Reg #{r.registration_number} · {r.date_stamped ?? "unknown date"}
                  </span>
                  <span
                    className="row-meta"
                    style={{ fontFamily: "var(--serif-body)", fontSize: 13, color: "var(--lunar)" }}
                  >
                    {renderSnippet(r.snippet)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
          {results.data.total > PAGE_SIZE && (
            <div className="pagination">
              <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
                &larr; Prev
              </button>
              <span className="row-meta">
                {offset + 1}–{Math.min(offset + PAGE_SIZE, results.data.total)} of {results.data.total}
              </span>
              <button disabled={offset + PAGE_SIZE >= results.data.total} onClick={() => setOffset(offset + PAGE_SIZE)}>
                Next &rarr;
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
