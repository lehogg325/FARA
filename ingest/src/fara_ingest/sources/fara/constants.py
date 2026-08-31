from __future__ import annotations

JURISDICTION = "fara"

BULK_BASE_URL = "https://efile.fara.gov/bulk/zip"

# Encoding confirmed live (docs/api-notes.md) and required — ISO-8859-1 accepts every
# byte value without raising, so decoding is safe even though no non-ASCII bytes were
# observed in the current snapshot; assuming UTF-8 would risk a future UnicodeDecodeError.
ENCODING = "iso-8859-1"

# Headers below are copied verbatim from a real download inspected on 2026-08-21
# (docs/api-notes.md) — not guessed from the API's human-readable docs.
DATASETS: dict[str, dict] = {
    "registrants": {
        "filename": "FARA_All_Registrants.csv.zip",
        "expected_header": [
            "Registration Number",
            "Registration Date",
            "Termination Date",
            "Name",
            "Business Name",
            "Address 1",
            "Address 2",
            "City",
            "State",
            "Zip",
        ],
    },
    "registrant_docs": {
        "filename": "FARA_All_RegistrantDocs.csv.zip",
        "expected_header": [
            "Date Stamped",
            "Registrant Name",
            "Registration Number",
            "Document Type",
            "Short Form Name",
            "Foreign Principal Name",
            "Foreign Principal Country",
            "URL",
        ],
    },
    "short_forms": {
        "filename": "FARA_All_ShortForms.csv.zip",
        "expected_header": [
            "Short Form Termination Date",
            "Short Form Date",
            "Short Form Last Name",
            "Short Form First Name",
            "Registration Number",
            "Registration Date",
            "Registrant Name",
            "Address 1",
            "Address 2",
            "City",
            "State",
            "Zip",
        ],
    },
    "foreign_principals": {
        "filename": "FARA_All_ForeignPrincipals.csv.zip",
        "expected_header": [
            "Foreign Principal Termination Date",
            "Foreign Principal",
            "Foreign Principal Registration Date",
            "Country/Location Represented",
            "Registration Number",
            "Registrant Date",
            "Registrant Name",
            "Address 1",
            "Address 2",
            "City",
            "State",
            "Zip",
        ],
    },
}

# Document Type vocabulary — confirmed closed and complete against a live pull
# (docs/api-notes.md): API's uppercase codes 1:1 with the bulk CSV's human labels.
DOCUMENT_TYPES: list[tuple[str, str]] = [
    ("REGISTRATION_STATEMENT", "Registration Statement"),
    ("SUPPLEMENTAL_STATEMENT", "Supplemental Statement"),
    ("SHORT-FORM", "Short-Form"),
    ("EXHIBIT_AB", "Exhibit AB"),
    ("EXHIBIT_C", "Exhibit C"),
    ("EXHIBIT_D", "Exhibit D"),
    ("AMENDMENT", "Amendment"),
    ("INFORMATIONAL_MATERIALS", "Informational Materials"),
    ("DISSEMINATION_REPORT", "Dissemination Report"),
    ("CONFLICT_PROVISION", "Conflict Provision"),
]

# Sentinel the bulk RegistrantDocs CSV uses in place of a URL for documents that
# only exist in DOJ's physical office (confirmed: 27,814 of 153,709 rows, docs/api-notes.md).
OFFICE_ONLY_URL_SENTINEL = "Available-FARA-Public-Office"
