import pytest
from fastapi import HTTPException

from app.routers.chat import _build_prompt_messages


def test_prompt_ends_at_target_and_excludes_future_messages():
    messages = [
        {"id": "u1", "role": "user", "content": "first question"},
        {"id": "a1", "role": "assistant", "content": "first answer"},
        {"id": "u2", "role": "user", "content": "target question"},
        {"id": "u3", "role": "user", "content": "future private context"},
    ]

    prompt = _build_prompt_messages(messages, "u2")

    assert prompt[0]["role"] == "system"
    assert [item["content"] for item in prompt[1:]] == [
        "first question",
        "first answer",
        "target question",
    ]


def test_prompt_rejects_non_user_or_missing_target():
    messages = [
        {"id": "a1", "role": "assistant", "content": "assistant turn"},
    ]

    with pytest.raises(HTTPException) as error:
        _build_prompt_messages(messages, "a1")
    assert error.value.status_code == 404

    with pytest.raises(HTTPException) as error:
        _build_prompt_messages(messages, "missing")
    assert error.value.status_code == 404


def test_prompt_bounds_message_count_and_total_characters():
    messages = [
        {"id": f"u{i}", "role": "user", "content": "x" * 8000}
        for i in range(35)
    ]

    prompt = _build_prompt_messages(messages, "u34")

    assert len(prompt) <= 31
    assert sum(len(item["content"]) for item in prompt[1:]) <= 24000
    assert prompt[-1]["content"] == "x" * 8000
