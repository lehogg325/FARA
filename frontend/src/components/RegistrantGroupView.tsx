import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { useStore } from "../state/store";

function fmtDate(d: string | null): string {
  return d ?? "—";
}

export function RegistrantGroupView({ name }: { name: string }) {
  const navigate = useStore((s) => s.navigate);
  const back = useStore((s) => s.back);
  const group = useQuery({ queryKey: ["registrants-by-name", name], queryFn: () => api.registrantsByName(name) });

  if (group.isLoading) return <div className="loading">Loading…</div>;
  if (group.isError || !group.data) return <div className="error-state">No registrants found with that name.</div>;
  const g = group.data;

  return (
    <div>
      <button className="back-link" onClick={back}>&larr; Back</button>

      <div className="record-kicker">Registrant · name match</div>
      <h2 className="record-title">{g.name}</h2>
      <div className="record-sub">
        {g.registrant_count} registration{g.registrant_count === 1 ? "" : "s"} on file under this name
      </div>

      <div className="group-card">
        <ul className="record-list">
          {g.registrants.map((r) => (
            <li key={r.registrant_id}>
              <button className="row-btn" onClick={() => navigate({ kind: "registrant", id: r.registrant_id })}>
                <span>
                  #{r.registration_number}
                  <span className={`status-pill ${r.status}`}>{r.status}</span>
                </span>
                <span className="row-meta">
                  {fmtDate(r.registration_date)} — {fmtDate(r.termination_date)}
                </span>
              </button>
            </li>
          ))}
        </ul>
      </div>

      <p className="group-card-note">
        Grouped by exact name match (case/whitespace-insensitive only) — each row is a
        distinct registration record, most often the same organization re-registering
        after a lapse or filing a fresh registration.
      </p>
    </div>
  );
}
