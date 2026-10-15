"""Worker credential boundaries and private storage checks without a running simulator."""

import io
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from botocore.response import StreamingBody
from botocore.stub import Stubber

from scripts.remote_worker import Api, ProtocolError
from src.services import remote_storage


def test_api_credential_scope_and_redacted_errors():
    for url in ("http://example.com", "https://user:password@example.com", "https://example.com?secret=x"):
        with pytest.raises(ValueError):
            Api(url, "worker", "a" * 40)
    api = Api("https://backend.test", "worker", "a" * 40)

    def handler(request):
        assert request.headers["Authorization"] == "Bearer " + "a" * 40
        assert request.url.path == "/api/v1/remote-workers/claim"
        return httpx.Response(401, text="unsafe-provider-detail")

    api.client.close()
    api.client = httpx.Client(base_url="https://backend.test/api/v1/remote-workers/",
                              headers={"Authorization": "Bearer " + "a" * 40},
                              transport=httpx.MockTransport(handler))
    with pytest.raises(ProtocolError) as error:
        api.post("claim")
    assert "unsafe" not in str(error.value) and "a" * 40 not in str(error.value)
    api.close()


def test_s3_signed_upload_and_stream_hash(monkeypatch):
    import hashlib
    from types import SimpleNamespace

    client = remote_storage.client("https://storage.test", "auto", "test-key", "test-secret")
    settings = SimpleNamespace(remote_storage_bucket="private")
    monkeypatch.setattr(remote_storage, "get_settings", lambda: settings)
    monkeypatch.setattr(remote_storage, "storage", lambda: client)
    raw = b"real uploaded bytes"
    record = {"path": "manifest.json", "object_key": "jobs/id/lease/manifest.json", "bytes": len(raw),
              "sha256": hashlib.sha256(raw).hexdigest()}
    signed = remote_storage.ticket(record)
    query = parse_qs(urlsplit(signed["url"]).query)
    assert "content-length" in query["X-Amz-SignedHeaders"][0]
    assert "x-amz-meta-sha256" in query["X-Amz-SignedHeaders"][0]
    assert "Authorization" not in signed["headers"]
    with Stubber(client) as stub:
        stub.add_response("get_object", {"ContentLength": len(raw), "Body": StreamingBody(io.BytesIO(raw), len(raw))},
                          {"Bucket": "private", "Key": record["object_key"]})
        assert remote_storage.read(record) == raw
    with Stubber(client) as stub:
        stub.add_response("get_object", {"ContentLength": len(raw), "Body": StreamingBody(io.BytesIO(b"x" * len(raw)), len(raw))},
                          {"Bucket": "private", "Key": record["object_key"]})
        with pytest.raises(ValueError, match="integrity"):
            remote_storage.verify(record)


def test_upload_renews_expired_url_and_retries_completion_without_credentials(tmp_path, monkeypatch):
    import hashlib
    import threading

    from scripts import remote_worker

    raw = b"abc"
    (tmp_path / "a.bin").write_bytes(raw)
    records = [{"path": "a.bin", "bytes": 3, "sha256": hashlib.sha256(raw).hexdigest()}]
    monkeypatch.setattr(remote_worker, "manifest", lambda *args: records)

    class FakeApi:
        tickets, completions = 0, 0

        def post(self, path, body):
            if path.endswith("/uploads"):
                self.tickets += 1
                return {"uploads": [{"path": "a.bin", "url": f"https://objects.test/a.bin?generation={self.tickets}",
                                     "headers": {"x-amz-meta-sha256": records[0]["sha256"]}}]}
            self.completions += 1
            if self.completions == 1:
                raise ProtocolError("Temporary backend outage", 503)
            return {"accepted": True}

    received = []

    def handler(request):
        assert "Authorization" not in request.headers
        assert request.headers["Content-Length"] == "3"
        assert request.read() == raw
        received.append(str(request.url))
        return httpx.Response(403 if len(received) == 1 else 200)

    real_client = httpx.Client
    monkeypatch.setattr(remote_worker.httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(handler)))
    api = FakeApi()
    assert remote_worker.upload(api, {"id": "a" * 32, "lease": "b" * 32}, tmp_path, {}, threading.Event())["accepted"]
    assert api.tickets == 2 and api.completions == 2
    assert "generation=2" in received[1]
