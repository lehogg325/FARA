from __future__ import annotations

import boto3
import pytest
from moto.server import ThreadedMotoServer

from fara_ingest.r2_archive import R2Archive

BUCKET = "fara-test-bucket"


@pytest.fixture
def archive():
    # moto's mock_aws() only intercepts recognized AWS hostnames — R2Archive
    # always talks to a custom endpoint_url (real R2's whole shape), so that
    # decorator never sees the traffic. A real local moto server, addressed
    # like any other S3-compatible endpoint, exercises the actual HTTP path.
    server = ThreadedMotoServer(port=0)
    server.start()
    endpoint_url = f"http://localhost:{server._server.socket.getsockname()[1]}"
    try:
        boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name="us-east-1",
            aws_access_key_id="test",
            aws_secret_access_key="test",
        ).create_bucket(Bucket=BUCKET)
        yield R2Archive(
            bucket=BUCKET, endpoint_url=endpoint_url, access_key_id="test", secret_access_key="test"
        )
    finally:
        server.stop()


def test_exists_false_for_missing_key(archive):
    assert archive.exists("fara/bulk/registrants/date=2026-08-21/x.csv.zip") is False


def test_write_then_read_round_trips(archive):
    key = "fara/bulk/registrants/date=2026-08-21/x.csv.zip"
    archive.write_atomic(key, b"real bytes")
    assert archive.exists(key) is True
    assert archive.read_bytes(key) == b"real bytes"


def test_write_atomic_overwrites_existing_key(archive):
    key = "fara/docs/5870/5870-Exhibit-AB.pdf"
    archive.write_atomic(key, b"first version")
    archive.write_atomic(key, b"second version")
    assert archive.read_bytes(key) == b"second version"
