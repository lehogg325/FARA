import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { useStore } from "../state/store";

function fmtDate(d: string | null): string {
  return d ?? "—";
}

export function ForeignPrincipalView({ id }: { id: number }) {
  const navigate = useStore((s) => s.navigate);
  const back = useStore((s) => s.back);
  const fp = useQuery({ queryKey: ["foreign-principal", id], queryFn: () => api.foreignPrincipal(id) });

  if (fp.isLoading) return <div className="loading">Loading…</div>;
  if (fp.isError || !fp.data) return <div className="error-state">Foreign principal not found.</div>;
  const f = fp.data;

  return (
    <div>
      <button className="back-link" onClick={back}>&larr; Back</button>

      <div className="record-kicker">Foreign principal</div>
      <h2 className="record-title">{f.foreign_principal_name}</h2>
      {f.country_raw && <div className="record-sub">{f.country_raw}</div>}

      <div className="record-fields">
        <div className="record-field">
          <div className="field-label">Location</div>
          <div className="field-value">{[f.city, f.state].filter(Boolean).join(", ") || "—"}</div>
        </div>
        <div className="record-field">
          <div className="field-label">Registered</div>
          <div className="field-value">{fmtDate(f.registration_date)}</div>
        </div>
        <div className="record-field">
          <div className="field-label">Terminated</div>
          <div className="field-value">{fmtDate(f.termination_date)}</div>
        </div>
      </div>

      <div className="section">
        <div className="section-title">Represented by</div>
        <ul className="record-list">
          <li>
            <button className="row-btn" onClick={() => navigate({ kind: "registrant", id: f.registrant_id })}>
              <span>Registrant #{f.registration_number}</span>
              <span className="row-meta">view registrant &rarr;</span>
            </button>
          </li>
        </ul>
      </div>

      <div className="section">
        <button
          className="back-link"
          onClick={() => navigate({ kind: "foreign-principal-group", name: f.foreign_principal_name, country: f.country_raw })}
        >
          See all registrants reporting "{f.foreign_principal_name}" &rarr;
        </button>
      </div>
    </div>
  );
}
