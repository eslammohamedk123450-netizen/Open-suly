from __future__ import annotations

from uuid import uuid4

import pytest

from app.services.engine_collaboration import (
    ArtifactReference, CollaborationEvent, EngineResultEnvelope,
    TaskContract, validate_artifact_handoff,
)

OWNER = str(uuid4())
TASK = str(uuid4())
RUN = str(uuid4())
ARTIFACT = ArtifactReference(
    artifact_id="artifact_12345678", owner_id=OWNER, project_id=None,
    sha256="a" * 64, byte_size=1024, media_type="text/plain",
)


def contract(**overrides):
    values = dict(
        task_id=TASK, owner_id=OWNER, parent_run_id=RUN,
        source_engine="hermes-agent", target_engine="opencode",
        capability="code.review", artifact_refs=(ARTIFACT,),
    )
    values.update(overrides)
    return TaskContract(**values)


def test_contract_accepts_isolated_cross_engine_handoff():
    contract().validate()


def test_contract_rejects_same_engine_and_invalid_depth():
    with pytest.raises(ValueError, match="same_engine"):
        contract(target_engine="hermes-agent").validate()
    with pytest.raises(ValueError, match="depth"):
        contract(depth=4).validate()


def test_contract_rejects_cross_owner_artifact():
    other = ArtifactReference(
        artifact_id="artifact_87654321", owner_id=str(uuid4()), project_id=None,
        sha256="b" * 64, byte_size=10, media_type="text/plain",
    )
    with pytest.raises(ValueError, match="owner_mismatch"):
        contract(artifact_refs=(other,)).validate()


def test_contract_rejects_unbounded_parallelism_and_duplicate_artifacts():
    with pytest.raises(ValueError, match="parallelism"):
        contract(max_child_tasks=1, max_parallel_children=2).validate()
    with pytest.raises(ValueError, match="duplicate_artifact"):
        contract(artifact_refs=(ARTIFACT, ARTIFACT)).validate()


def test_event_schema_rejects_free_text_and_invalid_status():
    event = CollaborationEvent(
        event_id=str(uuid4()), task_id=TASK, owner_id=OWNER,
        source_engine="hermes-agent", target_engine="opencode",
        event_type="handoff.started", status="running", sequence=1,
    )
    event.validate()
    with pytest.raises(ValueError, match="event_type"):
        CollaborationEvent(
            event_id=str(uuid4()), task_id=TASK, owner_id=OWNER,
            source_engine="hermes-agent", target_engine="opencode",
            event_type="handoff.prompt", status="running",
        ).validate()


def test_result_requires_expected_engine_and_bounded_usage():
    result = EngineResultEnvelope(
        task_id=TASK, owner_id=OWNER, engine_id="opencode",
        status="completed", artifact_refs=(ARTIFACT,),
        input_tokens=100, output_tokens=200, duration_ms=500,
    )
    result.validate(expected_engine="opencode")
    with pytest.raises(ValueError, match="engine_mismatch"):
        result.validate(expected_engine="hermes-agent")
    with pytest.raises(ValueError, match="input_tokens"):
        EngineResultEnvelope(
            task_id=TASK, owner_id=OWNER, engine_id="opencode",
            status="completed", artifact_refs=(), input_tokens=-1,
        ).validate(expected_engine="opencode")


def test_artifact_handoff_requires_approved_media_type():
    accepted = validate_artifact_handoff(
        (ARTIFACT,), owner_id=OWNER, target_engine="opencode",
        approved_media_types=frozenset({"text/plain"}),
    )
    assert accepted == (ARTIFACT,)
    with pytest.raises(ValueError, match="media_type_not_approved"):
        validate_artifact_handoff(
            (ARTIFACT,), owner_id=OWNER, target_engine="opencode",
            approved_media_types=frozenset({"application/pdf"}),
        )


def test_collaboration_prompt_treats_hermes_output_as_untrusted_context():
    from app.services.engine_collaboration import render_collaboration_prompt

    prompt = render_collaboration_prompt(
        source_engine="hermes-agent",
        source_output={"operation": "hermes.agent.turn", "content": "Review this project."},
        instructions="Apply the requested changes.",
    )
    assert "Review this project." in prompt
    assert "غير موثوقة" in prompt
    assert "<UNTRUSTED_ENGINE_OUTPUT>" in prompt


def test_collaboration_prompt_rejects_unbounded_or_unexpected_source_output():
    from app.services.engine_collaboration import render_collaboration_prompt

    with pytest.raises(ValueError, match="source_output_invalid"):
        render_collaboration_prompt(
            source_engine="hermes-agent",
            source_output={"content": "x" * 12_001},
            instructions="Review.",
        )
    with pytest.raises(ValueError, match="source_output_invalid"):
        render_collaboration_prompt(
            source_engine="opencode",
            source_output={"operation": "opencode.task.run", "prompt": "leak"},
            instructions="Review.",
        )


def test_collaboration_prompt_serializes_only_allowlisted_opencode_result_metadata():
    from app.services.engine_collaboration import render_collaboration_prompt

    prompt = render_collaboration_prompt(
        source_engine="opencode",
        source_output={
            "operation": "opencode.task.run",
            "change_set_id": "change_123",
            "status": "review_ready",
            "changed_count": 2,
            "requires_review": True,
        },
        instructions="Summarize the pending code change.",
    )
    assert "change_123" in prompt
    assert "changed_count" in prompt
    assert "prompt" not in prompt
