import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { useStore } from "../state/store";

export function ForeignPrincipalGroupView({ name, country }: { name: string; country: string | null }) {
  const navigate = useStore((s) => s.navigate);
  const back = useStore((s) => s.back);
  const groups = useQuery({
    queryKey: ["fp-by-name", name, country],
    queryFn: () => api.foreignPrincipalsByName(name, country ?? undefined),
  });

  if (groups.isLoading) return <div className="loading">Loading…</div>;
  if (groups.isError) return <div className="error-state">Could not load groups.</div>;

  const totalRegistrants = (groups.data ?? []).reduce((n, g) => n + g.registrant_count, 0);

  return (
    <div>
      <button className="back-link" onClick={back}>&larr; Back</button>

      <div className="record-kicker">Foreign principal · name match</div>
      <h2 className="record-title">"{name}"</h2>
      <div className="record-sub">
        {totalRegistrants} registrant{totalRegistrants === 1 ? "" : "s"} report a foreign principal with this exact name
      </div>

      {(groups.data ?? []).map((g) => (
        <div className="group-card" key={`${g.foreign_principal_name}-${g.country_raw}`}>
          <div className="group-card-header">
            {g.country_raw ?? "no country on file"} · {g.registrant_count} registrant{g.registrant_count === 1 ? "" : "s"}
          </div>
          <ul className="record-list">
            {g.registrants.map((reg) => (
              <li key={reg.registrant_id}>
                <button className="row-btn" onClick={() => navigate({ kind: "registrant", id: reg.registrant_id })}>
                  <span>{reg.name}</span>
                  <span className="row-meta">{reg.status} · #{reg.registration_number}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      ))}

      <p className="group-card-note">
        Grouped by exact name match only — FARA gives foreign principals no independent
        ID, so this is not a verified claim that these are the same real-world entity.
      </p>
    </div>
  );
}
