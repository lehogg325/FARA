import { useQuery } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { api } from "../api/client";
import { GraphView, type GraphViewHandle } from "./GraphView";
import { Tabs } from "./Tabs";
import { TopEntityList } from "./TopEntityList";
import { useStore } from "../state/store";

const DRILLDOWN_PAGE_SIZE = 25;

function fmtDate(d: string | null): string {
  return d ?? "—";
}

function fmtMoney(n: number): string {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(n);
}

function Pagination({ total, offset, setOffset }: { total: number; offset: number; setOffset: (o: number) => void }) {
  if (total <= DRILLDOWN_PAGE_SIZE) return null;
  return (
    <div className="pagination">
      <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - DRILLDOWN_PAGE_SIZE))}>&larr; Prev</button>
      <span className="row-meta">{offset + 1}–{Math.min(offset + DRILLDOWN_PAGE_SIZE, total)} of {total}</span>
      <button disabled={offset + DRILLDOWN_PAGE_SIZE >= total} onClick={() => setOffset(offset + DRILLDOWN_PAGE_SIZE)}>Next &rarr;</button>
    </div>
  );
}

function RegistrantsDrilldown({ name }: { name: string }) {
  const navigate = useStore((s) => s.navigate);
  const [offset, setOffset] = useState(0);
  const results = useQuery({
    queryKey: ["country-registrants", name, offset],
    queryFn: () => api.countryRegistrants(name, { status: "active", offset, limit: DRILLDOWN_PAGE_SIZE }),
  });
  if (results.isLoading) return <div className="loading">Loading…</div>;
  if (!results.data) return null;
  return (
    <div>
      <ul className="record-list">
        {results.data.items.map((r) => (
          <li key={r.registrant_id}>
            <button className="row-btn" onClick={() => navigate({ kind: "registrant", id: r.registrant_id })}>
              <span>{r.name}</span>
              <span className="row-meta">{[r.city, r.state].filter(Boolean).join(", ") || "—"}</span>
            </button>
          </li>
        ))}
        {results.data.items.length === 0 && <li className="loading">No matches.</li>}
      </ul>
      <Pagination total={results.data.total} offset={offset} setOffset={setOffset} />
    </div>
  );
}

function ForeignPrincipalsDrilldown({ name }: { name: string }) {
  const navigate = useStore((s) => s.navigate);
  const [offset, setOffset] = useState(0);
  const results = useQuery({
    queryKey: ["country-foreign-principals", name, offset],
    queryFn: () =>
      api.searchForeignPrincipals({ country: name, group_by_name: false, offset, limit: DRILLDOWN_PAGE_SIZE }),
  });
  if (results.isLoading) return <div className="loading">Loading…</div>;
  if (!results.data) return null;
  const items = results.data.items.filter((fp): fp is Extract<typeof fp, { foreign_principal_id: number }> =>
    "foreign_principal_id" in fp,
  );
  return (
    <div>
      <ul className="record-list">
        {items.map((fp) => (
          <li key={fp.foreign_principal_id}>
            <button className="row-btn" onClick={() => navigate({ kind: "foreign-principal", id: fp.foreign_principal_id })}>
              <span>{fp.foreign_principal_name}</span>
              <span className="row-meta">represented by {fp.registrant_name}</span>
            </button>
          </li>
        ))}
        {items.length === 0 && <li className="loading">No matches.</li>}
      </ul>
      <Pagination total={results.data.total} offset={offset} setOffset={setOffset} />
    </div>
  );
}

function ContactsDrilldown({ name }: { name: string }) {
  const navigate = useStore((s) => s.navigate);
  const [offset, setOffset] = useState(0);
  const results = useQuery({
    queryKey: ["country-contacts", name, offset],
    queryFn: () => api.countryContacts(name, offset, DRILLDOWN_PAGE_SIZE),
  });
  if (results.isLoading) return <div className="loading">Loading…</div>;
  if (!results.data) return null;
  return (
    <div>
      <ul className="record-list">
        {results.data.items.map((c) => (
          <li key={`${c.reportable_contact_id}`}>
            <button className="row-btn" onClick={() => navigate({ kind: "document", id: c.registrant_doc_id })}>
              <span>
                {c.contact_name_raw}
                {c.purpose && <span className="row-meta"> · {c.purpose}</span>}
              </span>
              <span className="row-meta">
                {c.registrant_name}
                {c.contact_method && ` · ${c.contact_method}`}
                {" · "}{fmtDate(c.contact_date)}
              </span>
            </button>
          </li>
        ))}
        {results.data.items.length === 0 && <li className="loading">No matches.</li>}
      </ul>
      <Pagination total={results.data.total} offset={offset} setOffset={setOffset} />
    </div>
  );
}

function ContributionsDrilldown({ name }: { name: string }) {
  const navigate = useStore((s) => s.navigate);
  const [offset, setOffset] = useState(0);
  const results = useQuery({
    queryKey: ["country-contributions", name, offset],
    queryFn: () => api.countryContributions(name, offset, DRILLDOWN_PAGE_SIZE),
  });
  if (results.isLoading) return <div className="loading">Loading…</div>;
  if (!results.data) return null;
  return (
    <div>
      <ul className="record-list">
        {results.data.items.map((c, i) => (
          <li key={`${c.registrant_doc_id}-${i}`}>
            <button className="row-btn" onClick={() => navigate({ kind: "document", id: c.registrant_doc_id })}>
              <span>{c.recipient_raw ?? "(no recipient recorded)"}</span>
              <span className="row-meta">
                {c.registrant_name}
                {c.amount !== null && ` · ${fmtMoney(c.amount)}`}
                {" · "}{fmtDate(c.contribution_date)}
              </span>
            </button>
          </li>
        ))}
        {results.data.items.length === 0 && <li className="loading">No matches.</li>}
      </ul>
      <Pagination total={results.data.total} offset={offset} setOffset={setOffset} />
    </div>
  );
}

type DrilldownKey = "registrants" | "foreign_principals" | "contacts" | "contributions";

function OverviewTab({ name }: { name: string }) {
  const detail = useQuery({ queryKey: ["country", name], queryFn: () => api.country(name) });
  const [expanded, setExpanded] = useState<DrilldownKey | null>(null);
  if (detail.isLoading) return <div className="loading">Loading…</div>;
  if (detail.isError || !detail.data) return <div className="error-state">Country not found.</div>;
  const d = detail.data;

  const toggle = (key: DrilldownKey) => setExpanded((prev) => (prev === key ? null : key));

  return (
    <div>
      <div className="record-fields">
        <button className={`record-field record-field-clickable${expanded === "registrants" ? " active" : ""}`} onClick={() => toggle("registrants")}>
          <div className="field-label">Active registrants</div>
          <div className="field-value">{d.active_registrant_count} <span style={{ color: "var(--gray)" }}>({d.total_registrant_count} all-time)</span></div>
        </button>
        <button className={`record-field record-field-clickable${expanded === "foreign_principals" ? " active" : ""}`} onClick={() => toggle("foreign_principals")}>
          <div className="field-label">Foreign principals</div>
          <div className="field-value">{d.foreign_principal_count}</div>
        </button>
        <button className={`record-field record-field-clickable${expanded === "contacts" ? " active" : ""}`} onClick={() => toggle("contacts")}>
          <div className="field-label">Reportable contacts</div>
          <div className="field-value">{d.contact_count}</div>
        </button>
        <button className={`record-field record-field-clickable${expanded === "contributions" ? " active" : ""}`} onClick={() => toggle("contributions")}>
          <div className="field-label">Political contributions</div>
          <div className="field-value">
            {d.contribution_count}
            {d.contribution_total !== null && ` (${fmtMoney(d.contribution_total)})`}
          </div>
        </button>
      </div>

      {expanded && (
        <div className="section">
          {expanded === "registrants" && <RegistrantsDrilldown name={name} />}
          {expanded === "foreign_principals" && <ForeignPrincipalsDrilldown name={name} />}
          {expanded === "contacts" && <ContactsDrilldown name={name} />}
          {expanded === "contributions" && <ContributionsDrilldown name={name} />}
        </div>
      )}

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

export function CountryView({ name, tab }: { name: string; tab?: "overview" | "network" | "topics" }) {
  const back = useStore((s) => s.back);

  return (
    <div>
      <button className="back-link" onClick={back}>&larr; Back</button>

      <div className="record-kicker">Country</div>
      <h2 className="record-title">{name}</h2>

      <Tabs
        key={tab}
        initial={tab}
        tabs={[
          { key: "overview", label: "Overview", content: <OverviewTab name={name} /> },
          { key: "network", label: "Network", content: <NetworkTab name={name} /> },
          { key: "topics", label: "Topics", content: <TopicsTab name={name} /> },
        ]}
      />
    </div>
  );
}
