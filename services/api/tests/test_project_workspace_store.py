from __future__ import annotations

from uuid import uuid4

import pytest

from app.services.project_workspace_store import ProjectWorkspaceError, ProjectWorkspaceStore


class Query:
    def __init__(self, tables, table):
        self.tables, self.name, self.filters, self.maximum = tables, table, [], None

    def select(self, *_args): return self
    def eq(self, key, value): self.filters.append((key, value)); return self
    def limit(self, value): self.maximum = value; return self
    def order(self, *_args, **_kwargs): return self
    def execute(self):
        rows = self.tables.get(self.name, [])
        for key, value in self.filters:
            rows = [r for r in rows if r.get(key) == value]
        return type("Response", (), {"data": rows[:self.maximum] if self.maximum else rows})()


class Client:
    def __init__(self, tables): self.tables = tables
    def table(self, name): return Query(self.tables, name)


def test_snapshot_is_owner_project_scoped_and_has_deterministic_content_revision():
    user, project = str(uuid4()), str(uuid4())
    client = Client({
        "projects": [{"id": project, "user_id": user}],
        "project_files": [
            {"project_id": project, "user_id": user, "path": "src/main.py", "content": "print('hi')", "size_bytes": 11, "updated_at": "now"},
            {"project_id": project, "user_id": user, "path": "README.md", "content": "hello", "size_bytes": 5, "updated_at": "now"},
            {"project_id": project, "user_id": str(uuid4()), "path": "secret.txt", "content": "no", "size_bytes": 2},
        ],
    })
    store = ProjectWorkspaceStore(client)
    first = store.snapshot(user_id=user, project_id=project)
    second = store.snapshot(user_id=user, project_id=project)
    assert first["file_count"] == 2
    assert first["revision"] == second["revision"]
    assert all("secret.txt" != f["path"] for f in first["files"])


def test_snapshot_refuses_env_files_and_traversal():
    user, project = str(uuid4()), str(uuid4())
    client = Client({
        "projects": [{"id": project, "user_id": user}],
        "project_files": [{"project_id": project, "user_id": user, "path": ".env.production", "content": "secret"}],
    })
    with pytest.raises(ValueError, match="workspace_path_reserved"):
        ProjectWorkspaceStore(client).snapshot(user_id=user, project_id=project)


def test_snapshot_refuses_missing_or_foreign_project():
    user, project = str(uuid4()), str(uuid4())
    client = Client({"projects": [], "project_files": []})
    with pytest.raises(ProjectWorkspaceError, match="project_not_found"):
        ProjectWorkspaceStore(client).snapshot(user_id=user, project_id=project)


def test_snapshot_rejects_project_file_over_limit():
    user, project = str(uuid4()), str(uuid4())
    rows = [{"project_id": project, "user_id": user, "path": "src/large.txt", "content": "x" * (256 * 1024 + 1)}]
    client = Client({"projects": [{"id": project, "user_id": user}], "project_files": rows})
    with pytest.raises(ProjectWorkspaceError, match="file_too_large"):
        ProjectWorkspaceStore(client).snapshot(user_id=user, project_id=project)
