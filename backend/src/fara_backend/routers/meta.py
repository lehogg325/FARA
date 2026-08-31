from __future__ import annotations

import psycopg
from fastapi import APIRouter, Depends, Query

from fara_backend.db import get_db
from fara_backend.schemas import (
    Country,
    DatasetStatus,
    DocumentType,
    ExtractionCoverage,
    HealthResponse,
    MetaResponse,
)

router = APIRouter(tags=["meta"])

# Mirrors the real target-doc-type sets in fara_extract's rule/llm stages
# (docs/extraction.md) — kept in sync by hand since this is a read-only
# reporting view, not the pipeline itself.
_RULES_TARGET_DOC_TYPES = ["REGISTRATION_STATEMENT", "SUPPLEMENTAL_STATEMENT", "SHORT-FORM", "EXHIBIT_AB"]
_LLM_TARGET_DOC_TYPES = ["EXHIBIT_AB"]


@router.get("/health", response_model=HealthResponse)
def health(conn: psycopg.Connection = Depends(get_db)) -> HealthResponse:
    conn.execute("SELECT 1")
    return HealthResponse(status="ok")


@router.get("/document-types", response_model=list[DocumentType])
def document_types(
    jurisdiction: str = Query("fara"), conn: psycopg.Connection = Depends(get_db)
) -> list[DocumentType]:
    rows = conn.execute(
        "SELECT document_type_code, document_type_label FROM document_types "
        "WHERE jurisdiction = %s ORDER BY document_type_label",
        (jurisdiction,),
    ).fetchall()
    return [DocumentType(**r) for r in rows]


@router.get("/countries", response_model=list[Country])
def countries(jurisdiction: str = Query("fara"), conn: psycopg.Connection = Depends(get_db)) -> list[Country]:
    rows = conn.execute(
        "SELECT country_name FROM countries WHERE jurisdiction = %s ORDER BY country_name", (jurisdiction,)
    ).fetchall()
    return [Country(**r) for r in rows]


@router.get("/meta", response_model=MetaResponse)
def meta(jurisdiction: str = Query("fara"), conn: psycopg.Connection = Depends(get_db)) -> MetaResponse:
    dataset_rows = conn.execute(
        """
        SELECT DISTINCT ON (dataset) dataset, snapshot_date, loaded_row_count, status, finished_at
        FROM load_runs
        WHERE jurisdiction = %s
        ORDER BY dataset, snapshot_date DESC
        """,
        (jurisdiction,),
    ).fetchall()

    data_as_of = conn.execute(
        "SELECT max(snapshot_date) AS data_as_of FROM load_runs WHERE jurisdiction = %s", (jurisdiction,)
    ).fetchone()["data_as_of"]

    text_row = conn.execute(
        """
        SELECT
            (SELECT count(*) FROM extraction_runs er JOIN registrant_docs rd ON rd.registrant_doc_id = er.registrant_doc_id
             WHERE rd.jurisdiction = %(j)s AND er.stage = 'text' AND er.status = 'succeeded') AS succeeded,
            (SELECT count(*) FROM registrant_docs WHERE jurisdiction = %(j)s AND pdf_object_key IS NOT NULL) AS eligible
        """,
        {"j": jurisdiction},
    ).fetchone()

    rules_row = conn.execute(
        """
        SELECT
            (SELECT count(*) FROM extraction_runs er JOIN registrant_docs rd ON rd.registrant_doc_id = er.registrant_doc_id
             WHERE rd.jurisdiction = %(j)s AND er.stage = 'fields_rule' AND er.status = 'succeeded') AS succeeded,
            (SELECT count(*) FROM registrant_docs rd JOIN document_text dt ON dt.registrant_doc_id = rd.registrant_doc_id
             WHERE rd.jurisdiction = %(j)s AND rd.document_type_code = ANY(%(doc_types)s)) AS eligible
        """,
        {"j": jurisdiction, "doc_types": _RULES_TARGET_DOC_TYPES},
    ).fetchone()

    llm_row = conn.execute(
        """
        SELECT
            (SELECT count(*) FROM extraction_runs er JOIN registrant_docs rd ON rd.registrant_doc_id = er.registrant_doc_id
             WHERE rd.jurisdiction = %(j)s AND er.stage = 'fields_llm' AND er.status = 'succeeded') AS succeeded,
            (SELECT count(*) FROM registrant_docs rd JOIN document_text dt ON dt.registrant_doc_id = rd.registrant_doc_id
             WHERE rd.jurisdiction = %(j)s AND rd.document_type_code = ANY(%(doc_types)s)) AS eligible
        """,
        {"j": jurisdiction, "doc_types": _LLM_TARGET_DOC_TYPES},
    ).fetchone()

    return MetaResponse(
        jurisdiction=jurisdiction,
        data_as_of=data_as_of,
        datasets=[DatasetStatus(**r) for r in dataset_rows],
        extraction_coverage=[
            ExtractionCoverage(stage="text", succeeded_count=text_row["succeeded"], eligible_count=text_row["eligible"]),
            ExtractionCoverage(
                stage="fields_rule", succeeded_count=rules_row["succeeded"], eligible_count=rules_row["eligible"]
            ),
            ExtractionCoverage(
                stage="fields_llm", succeeded_count=llm_row["succeeded"], eligible_count=llm_row["eligible"]
            ),
        ],
    )
