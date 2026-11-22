from app.routers import chat as chat_module


class _AttachmentQuery:
    def __init__(self, rows):
        self.rows = rows
        self.filters = {}
        self.ids = []

    def select(self, *_args):
        return self

    def eq(self, key, value):
        self.filters[key] = value
        return self

    def in_(self, key, values):
        assert key == "id"
        self.ids = values
        return self

    def limit(self, _value):
        return self

    def execute(self):
        rows = [
            row for row in self.rows
            if row["id"] in self.ids
            and row["user_id"] == self.filters["user_id"]
            and row["project_id"] == self.filters["project_id"]
        ]
        return type("Response", (), {"data": rows})()


class _AttachmentAdmin:
    def __init__(self, rows):
        self.rows = rows

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def table(self, name):
        assert name == "project_files"
        return _AttachmentQuery(self.rows)


def test_chat_attachment_context_is_owner_and_project_scoped(monkeypatch):
    file_id = "00000000-0000-0000-0000-000000000301"
    admin = _AttachmentAdmin([{
        "id": file_id,
        "user_id": "owner-a",
        "project_id": "00000000-0000-0000-0000-000000000302",
        "path": "src/main.py",
        "content": "print('hello')",
    }])
    monkeypatch.setattr(chat_module, "get_supabase_admin_client", lambda: admin)
    messages = [{
        "id": "00000000-0000-0000-0000-000000000303",
        "role": "user",
        "content": "Review this file",
        "metadata": {"attachments": [{"id": file_id, "path": "src/main.py"}]},
    }]

    chat_module._inject_target_attachments(
        messages,
        "00000000-0000-0000-0000-000000000303",
        "owner-a",
        "00000000-0000-0000-0000-000000000302",
    )

    assert "[Attached project file: src/main.py]" in messages[0]["content"]
    assert "print('hello')" in messages[0]["content"]


def test_chat_attachment_context_rejects_cross_project_file(monkeypatch):
    file_id = "00000000-0000-0000-0000-000000000311"
    admin = _AttachmentAdmin([{
        "id": file_id,
        "user_id": "owner-b",
        "project_id": "other-project",
        "path": "private.txt",
        "content": "private",
    }])
    monkeypatch.setattr(chat_module, "get_supabase_admin_client", lambda: admin)
    messages = [{
        "id": "00000000-0000-0000-0000-000000000313",
        "role": "user",
        "content": "Review",
        "metadata": {"attachments": [{"id": file_id, "path": "private.txt"}]},
    }]

    from fastapi import HTTPException
    import pytest

    with pytest.raises(HTTPException) as error:
        chat_module._inject_target_attachments(
            messages, "00000000-0000-0000-0000-000000000313", "owner-a", "project-a"
        )
    assert error.value.status_code == 404


def test_chat_attachment_context_rejects_missing_project():
    from fastapi import HTTPException
    import pytest

    messages = [{
        "id": "00000000-0000-0000-0000-000000000323",
        "role": "user",
        "content": "Review",
        "metadata": {"attachments": [{"id": "00000000-0000-0000-0000-000000000321"}]},
    }]
    with pytest.raises(HTTPException) as error:
        chat_module._inject_target_attachments(
            messages, "00000000-0000-0000-0000-000000000323", "owner-a", None
        )
    assert error.value.status_code == 422
