import importlib.util
import io
import json
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location("registry", Path(__file__).parents[1] / "scripts/check-registry.py")
registry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(registry)


def fake_registry(media_type=registry.DOCKER_MANIFEST, revision="commit", missing_digest=False, different_tags=False):
    requests = []
    def opener(request):
        if isinstance(request, str):
            body = {"token": "test-token"}
            headers = {}
        else:
            requests.append(request)
            assert request.get_header("Accept") == registry.ACCEPT
            digest = "sha256:" + ("b" if different_tags and request.full_url.endswith('/version') else "a") * 64
            headers = {} if missing_digest else {"Docker-Content-Digest": digest}
            body = ({"config": {"Labels": {"org.opencontainers.image.revision": revision}}}
                    if "/blobs/" in request.full_url else
                    {"mediaType": media_type, "config": {"digest": "sha256:" + "c" * 64}})
        response = io.BytesIO(json.dumps(body).encode())
        response.headers = headers
        return response
    return opener, requests


def test_legacy_unraid_head_and_tags():
    opener, requests = fake_registry()
    registry.verify("owner/repo", ["latest", "version"], "commit", opener)
    assert [r.get_method() for r in requests] == ["HEAD", "GET", "GET"] * 2


@pytest.mark.parametrize("options", [
    {"media_type": "application/vnd.oci.image.manifest.v1+json"},
    {"revision": "wrong"}, {"missing_digest": True}, {"different_tags": True},
])
def test_rejects_incompatible_or_wrong_publication(options):
    opener, _ = fake_registry(**options)
    with pytest.raises(ValueError):
        registry.verify("owner/repo", ["latest", "version"], "commit", opener)
