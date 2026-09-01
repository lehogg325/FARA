import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, type TopContact, type TopRecipient } from "../api/client";
import { useStore } from "../state/store";

const money = (n: number | null) =>
  n === null ? null : new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(n);

function Row({
  label, count, extra, docIds, onFocusNode, notFound,
}: {
  label: string; count: number; extra?: string | null; docIds: number[];
  onFocusNode?: (label: string) => void;
  notFound: string | null;
}) {
  const navigate = useStore((s) => s.navigate);
  return (
    <li>
      <div
        className="row-btn"
        style={{ flexDirection: "column", alignItems: "flex-start", gap: 3, cursor: onFocusNode ? "pointer" : "default" }}
        onClick={onFocusNode ? () => onFocusNode(label) : undefined}
        role={onFocusNode ? "button" : undefined}
      >
        <span title={label} style={{ display: "block", maxWidth: "100%", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {label}
        </span>
        <span className="row-meta">
          {count.toLocaleString()} occurrence{count === 1 ? "" : "s"}
          {extra ? ` · ${extra}` : ""}
          {docIds.slice(0, 3).map((id, i) => (
            <span key={id}>
              {i === 0 ? " · " : ", "}
              <button
                className="back-link"
                style={{ display: "inline", padding: 0 }}
                onClick={(e) => { e.stopPropagation(); navigate({ kind: "document", id }); }}
              >
                filing {id}
              </button>
            </span>
          ))}
        </span>
        {notFound === label && (
          <span className="row-meta" style={{ color: "var(--yellow)" }}>
            Not currently shown — expand this contact's registrant in the graph first.
          </span>
        )}
      </div>
    </li>
  );
}

export function TopEntityList({
  countryName, layout = "row", onFocusNode,
}: {
  countryName: string;
  layout?: "row" | "column";
  onFocusNode?: (label: string) => boolean;
}) {
  const contacts = useQuery({ queryKey: ["top-contacts", countryName], queryFn: () => api.topContacts(countryName) });
  const recipients = useQuery({ queryKey: ["top-recipients", countryName], queryFn: () => api.topRecipients(countryName) });
  const [notFound, setNotFound] = useState<string | null>(null);

  const handleFocus = onFocusNode
    ? (label: string) => {
        const found = onFocusNode(label);
        setNotFound(found ? null : label);
        if (found) return;
        setTimeout(() => setNotFound((cur) => (cur === label ? null : cur)), 3000);
      }
    : undefined;

  const hasContacts = (contacts.data ?? []).length > 0;
  const hasRecipients = (recipients.data ?? []).length > 0;
  if (!hasContacts && !hasRecipients && !contacts.isLoading && !recipients.isLoading) return null;

  return (
    <div className="section" style={{ display: "flex", gap: 24, flexWrap: "wrap", flexDirection: layout === "column" ? "column" : "row" }}>
      <div style={{ flex: "1 1 320px", minWidth: 240 }}>
        <div className="section-title">Top contacts</div>
        {contacts.isLoading && <div className="loading">Loading…</div>}
        {hasContacts && (
          <ul className="record-list">
            {(contacts.data as TopContact[]).map((c) => (
              <Row
                key={c.contact_name_raw} label={c.contact_name_raw} count={c.occurrence_count}
                docIds={c.sample_registrant_doc_ids} onFocusNode={handleFocus} notFound={notFound}
              />
            ))}
          </ul>
        )}
      </div>
      <div style={{ flex: "1 1 320px", minWidth: 240 }}>
        <div className="section-title">Top contribution recipients</div>
        {recipients.isLoading && <div className="loading">Loading…</div>}
        {hasRecipients && (
          <ul className="record-list">
            {(recipients.data as TopRecipient[]).map((r) => (
              <Row
                key={r.recipient_raw} label={r.recipient_raw} count={r.occurrence_count} extra={money(r.total_amount)}
                docIds={r.sample_registrant_doc_ids} onFocusNode={handleFocus} notFound={notFound}
              />
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
