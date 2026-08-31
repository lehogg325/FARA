from __future__ import annotations

from fara_ingest.manifest import Manifest


def test_unknown_key_has_no_status(tmp_path):
    m = Manifest(tmp_path / "manifest.sqlite3")
    assert m.get_status("fara", "registrants", "2026-08-21") is None


def test_start_then_verify_transitions_status(tmp_path):
    m = Manifest(tmp_path / "manifest.sqlite3")

    m.start("fara", "registrants", "2026-08-21")
    assert m.get_status("fara", "registrants", "2026-08-21") == "downloading"

    m.mark_verified(
        "fara",
        "registrants",
        "2026-08-21",
        archive_key="k",
        sha256="abc",
        byte_size=10,
        row_count=5,
        http_status=200,
    )
    assert m.get_status("fara", "registrants", "2026-08-21") == "verified"


def test_restart_after_failure_resets_to_downloading(tmp_path):
    m = Manifest(tmp_path / "manifest.sqlite3")

    m.start("fara", "registrants", "2026-08-21")
    m.mark_failed("fara", "registrants", "2026-08-21", error_message="boom")
    assert m.get_status("fara", "registrants", "2026-08-21") == "failed"

    # Simulating a restart after a kill/failure: start() must cleanly reset the row.
    m.start("fara", "registrants", "2026-08-21")
    assert m.get_status("fara", "registrants", "2026-08-21") == "downloading"


def test_manifest_persists_across_reopen(tmp_path):
    db_path = tmp_path / "manifest.sqlite3"

    m1 = Manifest(db_path)
    m1.start("fara", "registrants", "2026-08-21")

    m2 = Manifest(db_path)  # reopening, as a fresh process would after a restart
    assert m2.get_status("fara", "registrants", "2026-08-21") == "downloading"
