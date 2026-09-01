// Typed wrappers over the FARA backend API. All data comes from our own
// Postgres (mined from efile.fara.gov) — the browser never talks to FARA directly.

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export type EntityType = "registrant" | "foreign_principal" | "short_form_registrant" | "country";

export interface SearchResult {
  entity_type: EntityType;
  entity_id: number | null; // null for 'country' — navigate by label instead
  label: string;
  detail: string | null;
  registration_number: number | null;
}

export interface RegistrantSummary {
  registrant_id: number;
  jurisdiction: string;
  registration_number: number;
  name: string;
  business_name: string | null;
  city: string | null;
  state: string | null;
  status: "active" | "terminated";
  registration_date: string | null;
  termination_date: string | null;
}

export interface RegistrantDetail extends RegistrantSummary {
  address_1: string | null;
  address_2: string | null;
  zip: string | null;
  foreign_principal_count: number;
  short_form_registrant_count: number;
  document_count: number;
}

export interface ShortFormRegistrant {
  short_form_registrant_id: number;
  jurisdiction: string;
  parent_registrant_id: number;
  parent_registration_number: number;
  last_name: string | null;
  first_name: string | null;
  short_form_date: string | null;
  termination_date: string | null;
}

export interface ForeignPrincipal {
  foreign_principal_id: number;
  jurisdiction: string;
  registrant_id: number;
  registration_number: number;
  foreign_principal_name: string;
  country_raw: string | null;
  city: string | null;
  state: string | null;
  registration_date: string | null;
  termination_date: string | null;
  registrant_name: string;
  registrant_status: "active" | "terminated";
}

export type ForeignPrincipalSort = "registration_date_desc" | "name_asc" | "country_asc";

export interface ForeignPrincipalByNameGroup {
  foreign_principal_name: string;
  country_raw: string | null;
  registrant_count: number;
  registrants: RegistrantSummary[];
}

export interface RegistrantDoc {
  registrant_doc_id: number;
  jurisdiction: string;
  registrant_id: number;
  registration_number: number;
  date_stamped: string | null;
  document_type_code: string | null;
  document_type_raw_label: string;
  short_form_name: string | null;
  foreign_principal_name: string | null;
  foreign_principal_country_raw: string | null;
  url: string | null;
  url_available: boolean;
  pdf_object_key: string | null;
  pdf_byte_size: number | null;
  pdf_downloaded_at: string | null;
}

export interface DocumentText {
  registrant_doc_id: number;
  extracted_text: string;
  extraction_method: "native" | "ocr" | "mixed";
  page_count: number | null;
  char_count: number | null;
  quality_flag: "ok" | "low_confidence" | "failed";
  extractor_version: string;
  extracted_at: string;
}

export interface ExtractedField {
  document_extracted_field_id: number;
  registrant_doc_id: number;
  field_key: string;
  field_value_text: string | null;
  field_value_numeric: number | null;
  field_value_date: string | null;
  source_page: number | null;
  extraction_method: "rule" | "llm";
  extractor_version: string;
  confidence: number | null;
  extracted_at: string;
}

export interface DocumentSearchResult {
  registrant_doc_id: number;
  registration_number: number;
  document_type_raw_label: string;
  date_stamped: string | null;
  snippet: string;
}

export interface DocumentType {
  document_type_code: string;
  document_type_label: string;
}

export interface DatasetStatus {
  dataset: string;
  snapshot_date: string;
  loaded_row_count: number;
  status: string;
  finished_at: string | null;
}

export interface ExtractionCoverage {
  stage: string;
  succeeded_count: number;
  eligible_count: number;
}

export interface Meta {
  jurisdiction: string;
  data_as_of: string | null;
  datasets: DatasetStatus[];
  extraction_coverage: ExtractionCoverage[];
}

export interface Country {
  country_name: string;
  registrant_count: number;
  foreign_principal_count: number;
}

export interface CountryDetail {
  country_name: string;
  active_registrant_count: number;
  total_registrant_count: number;
  foreign_principal_count: number;
  contact_count: number;
  contribution_total: number | null;
  contribution_count: number;
}

export interface Topic {
  topic: string;
  topic_label: string;
}

export interface TopicCount {
  topic: string;
  topic_label: string;
  document_count: number;
}

export type GraphNodeType = "foreign_principal" | "registrant" | "contact" | "recipient";
export type GraphEdgeType = "represents" | "contacted" | "contributed";

export interface GraphNode {
  id: string;
  node_type: GraphNodeType;
  label: string;
  registration_number: number | null;
  contact_count: number | null;
  contribution_count: number | null;
  contribution_total: number | null;
}

export interface GraphEdge {
  source: string;
  target: string;
  edge_type: GraphEdgeType;
  registrant_doc_id: number | null;
  edge_date: string | null;
  amount: number | null;
  detail: string | null;
}

export interface CountryGraph {
  country_name: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
  omitted_registrant_count: number;
}

export interface RegistrantExpansion {
  registrant_id: number;
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface TopContact {
  contact_name_raw: string;
  occurrence_count: number;
  sample_registrant_doc_ids: number[];
}

export interface TopRecipient {
  recipient_raw: string;
  occurrence_count: number;
  total_amount: number | null;
  sample_registrant_doc_ids: number[];
}

async function get<T>(url: string, signal?: AbortSignal): Promise<T> {
  const r = await fetch(url, { signal });
  if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`);
  return r.json() as Promise<T>;
}

const qs = (params: Record<string, string | number | undefined>): string => {
  const search = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== "") search.set(k, String(v));
  }
  const s = search.toString();
  return s ? `?${s}` : "";
};

export const api = {
  meta: () => get<Meta>("/api/meta"),
  documentTypes: () => get<DocumentType[]>("/api/document-types"),

  search: (q: string, type?: EntityType, signal?: AbortSignal) =>
    get<SearchResult[]>(`/api/search${qs({ q, type, limit: 15 })}`, signal),

  registrant: (id: number) => get<RegistrantDetail>(`/api/registrants/${id}`),
  registrantForeignPrincipals: (id: number, offset = 0, limit = 25) =>
    get<Page<ForeignPrincipal>>(`/api/registrants/${id}/foreign-principals${qs({ offset, limit })}`),
  registrantShortForms: (id: number, offset = 0, limit = 25) =>
    get<Page<ShortFormRegistrant>>(`/api/registrants/${id}/short-form-registrants${qs({ offset, limit })}`),
  registrantDocuments: (id: number, offset = 0, limit = 25) =>
    get<Page<RegistrantDoc>>(`/api/registrants/${id}/documents${qs({ offset, limit })}`),

  foreignPrincipal: (id: number) => get<ForeignPrincipal>(`/api/foreign-principals/${id}`),
  foreignPrincipalsByName: (name: string, country?: string) =>
    get<ForeignPrincipalByNameGroup[]>(`/api/foreign-principals/by-name${qs({ name, country })}`),
  searchForeignPrincipals: (params: {
    q?: string; country?: string; status?: "active" | "terminated"; sort?: ForeignPrincipalSort;
    offset?: number; limit?: number;
  }) => get<Page<ForeignPrincipal>>(`/api/foreign-principals${qs(params)}`),

  document: (id: number) => get<RegistrantDoc>(`/api/documents/${id}`),
  documentText: (id: number) => get<DocumentText>(`/api/documents/${id}/text`),
  documentFields: (id: number) => get<ExtractedField[]>(`/api/documents/${id}/fields`),
  documentSearch: (q: string, offset = 0, limit = 25) =>
    get<Page<DocumentSearchResult>>(`/api/documents/search${qs({ q, offset, limit })}`),

  countries: () => get<Country[]>("/api/countries"),
  country: (name: string) => get<CountryDetail>(`/api/countries/${encodeURIComponent(name)}`),
  countryTopics: (name: string) => get<TopicCount[]>(`/api/countries/${encodeURIComponent(name)}/topics`),
  countryGraph: (name: string) => get<CountryGraph>(`/api/countries/${encodeURIComponent(name)}/graph`),
  expandRegistrant: (countryName: string, registrantId: number) =>
    get<RegistrantExpansion>(
      `/api/countries/${encodeURIComponent(countryName)}/graph/registrants/${registrantId}/expand`,
    ),
  topContacts: (name: string, limit = 25) =>
    get<TopContact[]>(`/api/countries/${encodeURIComponent(name)}/top-contacts${qs({ limit })}`),
  topRecipients: (name: string, limit = 25) =>
    get<TopRecipient[]>(`/api/countries/${encodeURIComponent(name)}/top-recipients${qs({ limit })}`),
  topics: () => get<Topic[]>("/api/topics"),
};
