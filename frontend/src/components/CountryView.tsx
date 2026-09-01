import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { GraphView } from "./GraphView";
import { TopEntityList } from "./TopEntityList";
import { useStore } from "../state/store";

export function CountryView({ name }: { name: string }) {
  const back = useStore((s) => s.back);
  const detail = useQuery({ queryKey: ["country", name], queryFn: () => api.country(name) });
  const topics = useQuery({ queryKey: ["country-topics", name], queryFn: () => api.countryTopics(name) });
  const graph = useQuery({ queryKey: ["country-graph", name], queryFn: () => api.countryGraph(name) });

  if (detail.isLoading) return <div className="loading">Loading…</div>;
  if (detail.isError || !detail.data) return <div className="error-state">Country not found.</div>;
  const d = detail.data;

  const maxCount = Math.max(1, ...topics.data?.map((t) => t.document_count) ?? [1]);

  return (
    <div>
      <button className="back-link" onClick={back}>&larr; Back</button>

      <div className="record-kicker">Country</div>
      <h2 className="record-title">{name}</h2>

      <div className="record-fields">
        <div className="record-field">
          <div className="field-label">Active registrants</div>
          <div className="field-value">{d.active_registrant_count} <span style={{ color: "var(--gray)" }}>({d.total_registrant_count} all-time)</span></div>
        </div>
        <div className="record-field">
          <div className="field-label">Foreign principals</div>
          <div className="field-value">{d.foreign_principal_count}</div>
        </div>
        <div className="record-field">
          <div className="field-label">Reportable contacts</div>
          <div className="field-value">{d.contact_count}</div>
        </div>
        <div className="record-field">
          <div className="field-label">Political contributions</div>
          <div className="field-value">
            {d.contribution_count}
            {d.contribution_total !== null && ` (${new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(d.contribution_total)})`}
          </div>
        </div>
      </div>

      <p className="group-card-note" style={{ marginTop: 12 }}>
        Reportable-contact and contribution figures include everything reported by
        registrants who represent {name}, even activity that may actually belong to
        another country the same registrant also represents — FARA's filings often
        don't record which specific foreign principal a contact or contribution was for.
      </p>

      <div className="section">
        <div className="section-title">What {name} is lobbying on</div>
        {topics.data && topics.data.length === 0 && <div className="loading">No topics classified yet.</div>}
        {topics.data && topics.data.length > 0 && (
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {topics.data.map((t) => (
              <div key={t.topic} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <div style={{ width: 220, fontFamily: "var(--serif-body)", fontSize: 13 }}>{t.topic_label}</div>
                <div style={{ flex: 1, background: "var(--panel)", borderRadius: 2, overflow: "hidden" }}>
                  <div
                    style={{
                      width: `${(t.document_count / maxCount) * 100}%`,
                      background: "var(--orange)",
                      height: 14,
                      minWidth: 3,
                    }}
                  />
                </div>
                <div className="row-meta" style={{ width: 30, textAlign: "right" }}>{t.document_count}</div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="section">
        <div className="section-title">Reportable-contact network</div>
        {graph.isLoading && <div className="loading">Loading graph…</div>}
        {graph.data && <GraphView countryName={name} data={graph.data} />}
      </div>

      <TopEntityList countryName={name} />
    </div>
  );
}
