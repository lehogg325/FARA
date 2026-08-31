import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api/client";
import { useStore } from "../state/store";

const PAGE_SIZE = 10;

function fmtDate(d: string | null): string {
  return d ?? "—";
}

export function RegistrantView({ id }: { id: number }) {
  const navigate = useStore((s) => s.navigate);
  const back = useStore((s) => s.back);
  const [fpOffset, setFpOffset] = useState(0);
  const [sfOffset, setSfOffset] = useState(0);
  const [docOffset, setDocOffset] = useState(0);

  const registrant = useQuery({ queryKey: ["registrant", id], queryFn: () => api.registrant(id) });
  const foreignPrincipals = useQuery({
    queryKey: ["registrant-fps", id, fpOffset],
    queryFn: () => api.registrantForeignPrincipals(id, fpOffset, PAGE_SIZE),
  });
  const shortForms = useQuery({
    queryKey: ["registrant-sfs", id, sfOffset],
    queryFn: () => api.registrantShortForms(id, sfOffset, PAGE_SIZE),
  });
  const documents = useQuery({
    queryKey: ["registrant-docs", id, docOffset],
    queryFn: () => api.registrantDocuments(id, docOffset, PAGE_SIZE),
  });

  if (registrant.isLoading) return <div className="loading">Loading…</div>;
  if (registrant.isError || !registrant.data) return <div className="error-state">Registrant not found.</div>;
  const r = registrant.data;

  return (
    <div>
      <button className="back-link" onClick={back}>&larr; Back</button>

      <div className="record-kicker">Registrant · #{r.registration_number}</div>
      <h2 className="record-title">
        {r.name}
        <span className={`status-pill ${r.status}`}>{r.status}</span>
      </h2>
      {r.business_name && <div className="record-sub">{r.business_name}</div>}

      <div className="record-fields">
        <div className="record-field">
          <div className="field-label">Address</div>
          <div className="field-value">
            {r.address_1 ?? "—"}{r.address_2 ? `, ${r.address_2}` : ""}<br />
            {[r.city, r.state, r.zip].filter(Boolean).join(", ") || "—"}
          </div>
        </div>
        <div className="record-field">
          <div className="field-label">Registered</div>
          <div className="field-value">{fmtDate(r.registration_date)}</div>
        </div>
        <div className="record-field">
          <div className="field-label">Terminated</div>
          <div className="field-value">{fmtDate(r.termination_date)}</div>
        </div>
      </div>

      <Section
        title="Foreign principals"
        count={r.foreign_principal_count}
        page={foreignPrincipals.data}
        offset={fpOffset}
        setOffset={setFpOffset}
        renderItem={(fp) => (
          <button className="row-btn" onClick={() => navigate({ kind: "foreign-principal", id: fp.foreign_principal_id })}>
            <span>{fp.foreign_principal_name}</span>
            <span className="row-meta">{fp.country_raw ?? "—"} · {fmtDate(fp.registration_date)}</span>
          </button>
        )}
        keyOf={(fp) => fp.foreign_principal_id}
      />

      <Section
        title="Registered agents (short-form)"
        count={r.short_form_registrant_count}
        page={shortForms.data}
        offset={sfOffset}
        setOffset={setSfOffset}
        renderItem={(sf) => (
          <div className="row-btn" style={{ cursor: "default" }}>
            <span>{[sf.first_name, sf.last_name].filter(Boolean).join(" ") || "(unnamed)"}</span>
            <span className="row-meta">{fmtDate(sf.short_form_date)}</span>
          </div>
        )}
        keyOf={(sf) => sf.short_form_registrant_id}
      />

      <Section
        title="Documents"
        count={r.document_count}
        page={documents.data}
        offset={docOffset}
        setOffset={setDocOffset}
        renderItem={(doc) => (
          <button className="row-btn" onClick={() => navigate({ kind: "document", id: doc.registrant_doc_id })}>
            <span>{doc.document_type_raw_label}</span>
            <span className="row-meta">{fmtDate(doc.date_stamped)}</span>
          </button>
        )}
        keyOf={(doc) => doc.registrant_doc_id}
      />
    </div>
  );
}

function Section<T>({
  title, count, page, offset, setOffset, renderItem, keyOf,
}: {
  title: string;
  count: number;
  page: { items: T[]; total: number } | undefined;
  offset: number;
  setOffset: (n: number) => void;
  renderItem: (item: T) => React.ReactNode;
  keyOf: (item: T) => number;
}) {
  return (
    <div className="section">
      <div className="section-title">
        {title} <span className="count">({count.toLocaleString()})</span>
      </div>
      {!page ? (
        <div className="loading">Loading…</div>
      ) : page.items.length === 0 ? (
        <div className="loading">None on file.</div>
      ) : (
        <>
          <ul className="record-list">
            {page.items.map((item) => (
              <li key={keyOf(item)}>{renderItem(item)}</li>
            ))}
          </ul>
          {page.total > PAGE_SIZE && (
            <div className="pagination">
              <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
                &larr; Prev
              </button>
              <span className="row-meta">
                {offset + 1}–{Math.min(offset + PAGE_SIZE, page.total)} of {page.total}
              </span>
              <button disabled={offset + PAGE_SIZE >= page.total} onClick={() => setOffset(offset + PAGE_SIZE)}>
                Next &rarr;
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
