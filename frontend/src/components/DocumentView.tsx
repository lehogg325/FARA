import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, type ExtractedField } from "../api/client";
import { useStore } from "../state/store";

const FIELD_LABELS: Record<string, string> = {
  nature_of_activities: "Nature of activities",
  includes_political_activity: "Includes political activity",
  political_activity_description: "Political activity description",
  compensation_terms: "Compensation terms",
  agreement_date: "Agreement date",
};

function fieldLabel(key: string): string {
  if (key.startsWith("political_contribution[")) return "Political contribution";
  return FIELD_LABELS[key] ?? key.replace(/_/g, " ");
}

function money(n: number | null): string | null {
  if (n === null) return null;
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(n);
}

function FieldBlock({ field }: { field: ExtractedField }) {
  if (field.field_key === "includes_political_activity") {
    const isTrue = field.field_value_text === "true";
    return (
      <div className="field-block">
        <div className="field-key">{fieldLabel(field.field_key)}</div>
        <div className={`field-text ${isTrue ? "bool-true" : "bool-false"}`}>{isTrue ? "Yes" : "No"}</div>
      </div>
    );
  }

  if (field.field_key.startsWith("political_contribution[")) {
    return (
      <div className="field-block">
        <div className="field-key">{fieldLabel(field.field_key)}</div>
        <div className="field-text">
          {field.field_value_text ?? "—"}
          {field.field_value_numeric !== null && ` — ${money(field.field_value_numeric)}`}
          {field.field_value_date && ` (${field.field_value_date})`}
        </div>
      </div>
    );
  }

  if (field.field_key === "agreement_date") {
    return (
      <div className="field-block">
        <div className="field-key">{fieldLabel(field.field_key)}</div>
        <div className="field-text">{field.field_value_date ?? "—"}</div>
      </div>
    );
  }

  return (
    <div className="field-block">
      <div className="field-key">
        {fieldLabel(field.field_key)}
        <span className="extraction-tag">{field.extraction_method}</span>
      </div>
      <div className="field-text">{field.field_value_text ?? "—"}</div>
    </div>
  );
}

export function DocumentView({ id }: { id: number }) {
  const back = useStore((s) => s.back);
  const [showFullText, setShowFullText] = useState(false);

  const doc = useQuery({ queryKey: ["doc", id], queryFn: () => api.document(id) });
  const fields = useQuery({ queryKey: ["doc-fields", id], queryFn: () => api.documentFields(id) });
  const text = useQuery({ queryKey: ["doc-text", id], queryFn: () => api.documentText(id), retry: false });

  const ruleFields = (fields.data ?? []).filter((f) => f.extraction_method === "rule");
  const llmFields = (fields.data ?? []).filter((f) => f.extraction_method === "llm");

  if (doc.isError) return <div className="error-state">Document not found.</div>;

  return (
    <div>
      <button className="back-link" onClick={back}>&larr; Back</button>

      <div className="record-kicker">
        {doc.data ? `${doc.data.document_type_raw_label} · Reg #${doc.data.registration_number}` : `Document #${id}`}
      </div>
      <h2 className="record-title">{doc.data?.document_type_raw_label ?? "Filing detail"}</h2>
      {doc.data && (
        <div className="record-sub">
          Filed {doc.data.date_stamped ?? "unknown date"}
          {doc.data.foreign_principal_name && ` · re: ${doc.data.foreign_principal_name}`}
        </div>
      )}

      <div className="doc-body">
        {fields.isLoading && <div className="loading">Loading extracted fields…</div>}

        {ruleFields.length > 0 && (
          <>
            <h3>Structured fields (rule-extracted)</h3>
            {ruleFields.map((f) => (
              <FieldBlock key={f.document_extracted_field_id} field={f} />
            ))}
          </>
        )}

        {llmFields.length > 0 && (
          <>
            <h3>Narrative fields (LLM-assisted extraction)</h3>
            {llmFields.map((f) => (
              <FieldBlock key={f.document_extracted_field_id} field={f} />
            ))}
          </>
        )}

        {!fields.isLoading && ruleFields.length === 0 && llmFields.length === 0 && (
          <p style={{ fontStyle: "italic", color: "#6d6152" }}>
            No structured fields extracted for this document yet.
          </p>
        )}

        {text.data && (
          <>
            <h3>
              Full extracted text
              <span className="extraction-tag">
                {text.data.extraction_method} · {text.data.quality_flag}
              </span>
            </h3>
            {showFullText ? (
              <div className="doc-text">{text.data.extracted_text}</div>
            ) : (
              <button className="back-link" onClick={() => setShowFullText(true)}>
                Show full text ({text.data.char_count?.toLocaleString() ?? "?"} chars, {text.data.page_count ?? "?"} pages)
              </button>
            )}
          </>
        )}

        {doc.data?.url_available && doc.data.url && (
          <div className="doc-actions">
            <a href={doc.data.url} target="_blank" rel="noreferrer">
              View source PDF on efile.fara.gov
            </a>
          </div>
        )}
      </div>
    </div>
  );
}
