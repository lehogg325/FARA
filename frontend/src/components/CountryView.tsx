import { useQuery } from "@tanstack/react-query";
import { useRef } from "react";
import { api } from "../api/client";
import { GraphView, type GraphViewHandle } from "./GraphView";
import { Tabs } from "./Tabs";
import { TopEntityList } from "./TopEntityList";
import { useStore } from "../state/store";

function OverviewTab({ name }: { name: string }) {
  const detail = useQuery({ queryKey: ["country", name], queryFn: () => api.country(name) });
  if (detail.isLoading) return <div className="loading">Loading…</div>;
  if (detail.isError || !detail.data) return <div className="error-state">Country not found.</div>;
  const d = detail.data;

  return (
    <div>
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
    </div>
  );
}

function TopicsTab({ name }: { name: string }) {
  const topics = useQuery({ queryKey: ["country-topics", name], queryFn: () => api.countryTopics(name) });
  const maxCount = Math.max(1, ...(topics.data?.map((t) => t.document_count) ?? [1]));

  return (
    <div className="section" style={{ marginTop: 0 }}>
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
  );
}

function NetworkTab({ name }: { name: string }) {
  const graph = useQuery({ queryKey: ["country-graph", name], queryFn: () => api.countryGraph(name) });
  const graphRef = useRef<GraphViewHandle>(null);

  return (
    <div style={{ display: "flex", gap: 24, flexWrap: "wrap", alignItems: "flex-start" }}>
      <div style={{ flex: "2 1 520px", minWidth: 320 }}>
        {graph.isLoading && <div className="loading">Loading graph…</div>}
        {graph.data && <GraphView ref={graphRef} countryName={name} data={graph.data} />}
      </div>
      <div style={{ flex: "1 1 280px", minWidth: 260 }}>
        <TopEntityList
          countryName={name}
          layout="column"
          onFocusNode={(label) => graphRef.current?.focusByLabel(label) ?? false}
        />
      </div>
    </div>
  );
}

export function CountryView({ name }: { name: string }) {
  const back = useStore((s) => s.back);

  return (
    <div>
      <button className="back-link" onClick={back}>&larr; Back</button>

      <div className="record-kicker">Country</div>
      <h2 className="record-title">{name}</h2>

      <Tabs
        tabs={[
          { key: "overview", label: "Overview", content: <OverviewTab name={name} /> },
          { key: "network", label: "Network", content: <NetworkTab name={name} /> },
          { key: "topics", label: "Topics", content: <TopicsTab name={name} /> },
        ]}
      />
    </div>
  );
}
