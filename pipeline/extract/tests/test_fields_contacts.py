from __future__ import annotations

from fara_extract.fields_contacts import _looks_populated, find_populated_contact_windows

# All three verbatim from real 2025-2026 filings (docs/phase2.md), confirmed live
# against the actual document_text rows via direct query — not synthesized.

_QATAR_POPULATED = (
    "Received by NSD/FARA Registration Unit 08/01/2026 3:12:00 PM\n"
    "11. Set forth below in the required detail the registrant's political activities.\n"
    "Date Contact Method Purpose\n"
    "Embassy of the State 03/26/2026 Rachel Oglesby, Email U.S.-Qatar relations\n"
    "of Qatar Jennifer Chong,\n"
    "Dept of Education\n"
    "04/24/2026 Rachel Oglesby, Email U.S.-Qatar relations\n"
    "Embassy of the State Jennifer Chong,\n"
    "of Qatar Dept of Education\n"
    "07/17/2026 Yigal Carmon, Email U.S.-Qatar relations\n"
    "MEMRI\n"
    "Embassy of the State\n"
    "of Qatar\n"
    "13. In addition to the above described activities..."
)

_BRAZIL_POPULATED = (
    "Date Contact Method Purpose\n"
    "Invest SP - Agéncia 06/18/2026 State Department In person. Assist Brazilian Ambassador\n"
    "Paulista de Promocao in meeting with State\n"
    "de Investimentos e Department officials\n"
    "Competitividade concerning Section 301\n"
    "investigation of Brazil.\n"
    "06/30/2026 FN U.S., Inc. E-mail, telephone. Assisted FN U.S., Inc., to\n"
    "Invest SP - Agéncia prepare for Congressional\n"
    "de Investimentos e 301 Investigation of Brazil.\n"
    "Received by NSD/FARA Registration Unit 09/02/2026 1:00:00 PM"
)

_BLANK_TABLE = (
    "Date Contact Method Purpose\n"
    "Received by NSD/FARA Registration Unit 03/10/2025 11:37:17 AM\n"
    "12. During the period beginning 60 days prior to the obligation to register..."
)

_APPENDIX_DEFERRED = (
    "Date Contact Method Purpose\nSee Appendix for Response\n"
    "Received by NSD/FARA Registration Unit 08/15/2026 3:56:13 PM"
)


def test_looks_populated_true_for_real_data_rows():
    assert _looks_populated(_QATAR_POPULATED.split("Date Contact Method Purpose\n", 1)[1])


def test_looks_populated_false_for_blank_table():
    # In the real pipeline, _looks_populated only ever sees text already
    # truncated at _STOP_RE — simulate that truncation here rather than the
    # untruncated tail, which would spuriously match on the date in the
    # "Received by NSD/FARA...03/10/2025" stamp itself.
    assert not _looks_populated("\n")


def test_looks_populated_false_for_appendix_deferral():
    assert not _looks_populated(_APPENDIX_DEFERRED.split("Date Contact Method Purpose\n", 1)[1])


def test_find_windows_extracts_populated_table_stopping_before_next_item():
    windows = find_populated_contact_windows(_QATAR_POPULATED)
    assert len(windows) == 1
    assert "Rachel Oglesby" in windows[0]
    assert "Yigal Carmon" in windows[0]
    assert "13. In addition" not in windows[0]  # stopped before the next item


def test_find_windows_stops_before_received_by_stamp():
    windows = find_populated_contact_windows(_BRAZIL_POPULATED)
    assert len(windows) == 1
    assert "Section 301" in windows[0]
    assert "Received by NSD/FARA" not in windows[0]


def test_find_windows_empty_for_blank_table():
    assert find_populated_contact_windows(_BLANK_TABLE) == []


def test_find_windows_empty_for_appendix_deferral():
    assert find_populated_contact_windows(_APPENDIX_DEFERRED) == []


def test_find_windows_multiple_occurrences_in_one_document():
    combined = _QATAR_POPULATED + "\n\n" + _BLANK_TABLE
    windows = find_populated_contact_windows(combined)
    assert len(windows) == 1  # only the populated one survives the filter
