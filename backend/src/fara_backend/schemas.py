from __future__ import annotations

from datetime import date, datetime
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class RegistrantSummary(BaseModel):
    registrant_id: int
    jurisdiction: str
    registration_number: int
    name: str
    business_name: str | None
    city: str | None
    state: str | None
    status: str
    registration_date: date | None
    termination_date: date | None


class RegistrantDetail(RegistrantSummary):
    address_1: str | None
    address_2: str | None
    zip: str | None
    foreign_principal_count: int
    short_form_registrant_count: int
    document_count: int


class ShortFormRegistrant(BaseModel):
    short_form_registrant_id: int
    jurisdiction: str
    parent_registrant_id: int
    parent_registration_number: int
    last_name: str | None
    first_name: str | None
    short_form_date: date | None
    termination_date: date | None


class ForeignPrincipal(BaseModel):
    foreign_principal_id: int
    jurisdiction: str
    registrant_id: int
    registration_number: int
    foreign_principal_name: str
    country_raw: str | None
    city: str | None
    state: str | None
    registration_date: date | None
    termination_date: date | None


class ForeignPrincipalByNameGroup(BaseModel):
    foreign_principal_name: str
    country_raw: str | None
    registrant_count: int
    registrants: list[RegistrantSummary]


class RegistrantDoc(BaseModel):
    registrant_doc_id: int
    jurisdiction: str
    registrant_id: int
    registration_number: int
    date_stamped: date | None
    document_type_code: str | None
    document_type_raw_label: str
    short_form_name: str | None
    foreign_principal_name: str | None
    foreign_principal_country_raw: str | None
    url: str | None
    url_available: bool
    pdf_object_key: str | None
    pdf_byte_size: int | None
    pdf_downloaded_at: datetime | None


class DocumentText(BaseModel):
    registrant_doc_id: int
    extracted_text: str
    extraction_method: str
    page_count: int | None
    char_count: int | None
    quality_flag: str
    extractor_version: str
    extracted_at: datetime


class ExtractedField(BaseModel):
    document_extracted_field_id: int
    registrant_doc_id: int
    field_key: str
    field_value_text: str | None
    field_value_numeric: float | None
    field_value_date: date | None
    source_page: int | None
    extraction_method: str
    extractor_version: str
    confidence: float | None
    extracted_at: datetime


class DocumentSearchResult(BaseModel):
    registrant_doc_id: int
    registration_number: int
    document_type_raw_label: str
    date_stamped: date | None
    snippet: str


class SearchResult(BaseModel):
    entity_type: str  # 'registrant' | 'foreign_principal' | 'short_form_registrant' | 'country'
    entity_id: int | None  # null for 'country' — navigate by label (the country name) instead
    label: str
    detail: str | None
    registration_number: int | None


class DocumentType(BaseModel):
    document_type_code: str
    document_type_label: str


class Country(BaseModel):
    country_name: str
    registrant_count: int
    foreign_principal_count: int


class CountryDetail(BaseModel):
    country_name: str
    active_registrant_count: int
    total_registrant_count: int
    foreign_principal_count: int
    contact_count: int
    contribution_total: float | None
    contribution_count: int


class Topic(BaseModel):
    topic: str
    topic_label: str


class TopicCount(BaseModel):
    topic: str
    topic_label: str
    document_count: int


class GraphNode(BaseModel):
    id: str
    node_type: str  # 'foreign_principal' | 'registrant' | 'contact' | 'recipient'
    label: str
    registration_number: int | None = None
    # Populated on 'registrant' nodes in the backbone graph — how active that
    # registrant is, so the frontend can size/color without needing the
    # individual contact/recipient nodes loaded yet.
    contact_count: int | None = None
    contribution_count: int | None = None
    contribution_total: float | None = None


class GraphEdge(BaseModel):
    source: str
    target: str
    edge_type: str  # 'represents' | 'contacted' | 'contributed'
    registrant_doc_id: int | None
    edge_date: date | None = None
    amount: float | None = None
    detail: str | None = None


class CountryGraph(BaseModel):
    country_name: str
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    # How many additional (lower-activity) registrants exist for this country
    # beyond what's shown — 0 when nothing was omitted. Replaces a binary
    # 'truncated' flag with an honest, importance-ordered count.
    omitted_registrant_count: int = 0


class RegistrantExpansion(BaseModel):
    registrant_id: int
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class TopContact(BaseModel):
    contact_name_raw: str
    occurrence_count: int
    sample_registrant_doc_ids: list[int]


class TopRecipient(BaseModel):
    recipient_raw: str
    occurrence_count: int
    total_amount: float | None
    sample_registrant_doc_ids: list[int]


class DatasetStatus(BaseModel):
    dataset: str
    snapshot_date: date
    loaded_row_count: int
    status: str
    finished_at: datetime | None


class ExtractionCoverage(BaseModel):
    stage: str
    succeeded_count: int
    eligible_count: int


class MetaResponse(BaseModel):
    jurisdiction: str
    data_as_of: date | None
    datasets: list[DatasetStatus]
    extraction_coverage: list[ExtractionCoverage]


class HealthResponse(BaseModel):
    status: str
