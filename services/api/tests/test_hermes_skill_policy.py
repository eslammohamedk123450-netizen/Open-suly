import hashlib
from uuid import uuid4

import pytest

from app.services.hermes_skill_policy import validate_skill_package, HermesSkillApprovalStore


REVISION = "a" * 40


def test_skill_package_is_pinned_bounded_and_digest_verified():
    raw = b"name: helper\n"
    result = validate_skill_package(
        name="helper", content=raw, source_revision=REVISION, license_id="MIT"
    )
    assert result["content_sha256"] == hashlib.sha256(raw).hexdigest()
    assert result["content_bytes"] == len(raw)
    assert result["enabled"] is False
    assert result["status"] == "pending"


@pytest.mark.parametrize("kwargs,error", [
    ({"name": "../escape"}, "name_invalid"),
    ({"source_revision": "main"}, "revision_invalid"),
    ({"license_id": "UNKNOWN"}, "license_not_approved"),
    ({"content": b"\xff"}, "must_be_utf8"),
    ({"content": b""}, "size_invalid"),
])
def test_skill_package_rejects_untrusted_metadata(kwargs, error):
    values = {
        "name": "helper", "content": b"ok", "source_revision": REVISION,
        "license_id": "MIT",
    }
    values.update(kwargs)
    with pytest.raises(ValueError, match=error):
        validate_skill_package(**values)


def test_skill_package_rejects_oversized_content():
    with pytest.raises(ValueError, match="size_invalid"):
        validate_skill_package(
            name="helper", content=b"x" * (256 * 1024 + 1),
            source_revision=REVISION, license_id="MIT",
        )


def test_skill_store_never_activates_candidate_during_registration():
    class Query:
        def upsert(self, payload, **_kwargs):
            self.payload = payload
            return self
        def execute(self):
            return type("Result", (), {"data": [{**self.payload, "id": str(uuid4())}]})()
    class Client:
        def __init__(self): self.query = Query()
        def table(self, _name): return self.query

    client = Client()
    store = HermesSkillApprovalStore(client)
    package = validate_skill_package(
        name="helper", content=b"skill", source_revision=REVISION, license_id="MIT"
    )
    package.pop("status")
    package.pop("enabled")
    saved = store.register_candidate(user_id=str(uuid4()), package=package)
    assert saved["enabled"] is False
    assert saved["status"] == "pending"
