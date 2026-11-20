from types import SimpleNamespace

from app.services.tool_approvals import ToolApprovalStore


class FakeQuery:
    def __init__(self, data):
        self.data = data
        self.filters = []
        self.selected = None
        self.limit_value = None

    def select(self, value):
        return self

    def eq(self, key, value):
        self.filters.append((key, value))
        return self

    def is_(self, key, value):
        self.filters.append((key, value))
        return self

    def order(self, *args, **kwargs):
        return self

    def limit(self, value):
        self.limit_value = value
        return self

    def execute(self):
        rows = self.data
        for key, value in self.filters:
            if value == "null":
                rows = [row for row in rows if row.get(key) is None]
            else:
                rows = [row for row in rows if row.get(key) == value]
        return SimpleNamespace(data=rows)


class FakeClient:
    def __init__(self):
        self.calls = []
        self.rows = []
        self.rpc_result = None
        self.last_query = None

    def table(self, name):
        self.calls.append(("table", name))
        self.last_query = FakeQuery(self.rows)
        return self.last_query

    def rpc(self, name, args):
        self.calls.append(("rpc", name, args))
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=self.rpc_result))


def test_active_scopes_are_loaded_only_for_requested_owner():
    client = FakeClient()
    client.rows = [
        {"permission_scope": "files.read", "user_id": "user-1", "revoked_at": None},
        {"permission_scope": "web.search", "user_id": "user-1", "revoked_at": None},
        {"permission_scope": "admin.root", "user_id": "user-2", "revoked_at": None},
        {"permission_scope": "files.write", "user_id": "user-1", "revoked_at": "2026-11-20T00:00:00Z"},
    ]
    scopes = ToolApprovalStore(client).active_scopes("user-1")
    assert scopes == frozenset({"files.read", "web.search"})
    assert ("user_id", "user-1") in client.last_query.filters
    assert ("revoked_at", "null") in client.last_query.filters
    assert client.last_query.limit_value == 200


def test_grant_rpc_uses_authenticated_owner_as_actor_not_request_input():
    client = FakeClient()
    client.rpc_result = "approval-1"
    result = ToolApprovalStore(client).grant("user-1", "files.read")
    assert result == "approval-1"
    name, rpc_name, args = client.calls[0]
    assert rpc_name == "grant_tool_approval"
    assert args == {
        "p_user_id": "user-1",
        "p_permission_scope": "files.read",
        "p_actor_user_id": "user-1",
    }


def test_revoke_returns_false_when_no_active_grant_exists():
    client = FakeClient()
    client.rpc_result = 0
    assert ToolApprovalStore(client).revoke("user-1", "files.read") is False


def test_revoke_returns_true_when_a_grant_was_revoked():
    client = FakeClient()
    client.rpc_result = 1
    assert ToolApprovalStore(client).revoke("user-1", "files.read") is True


def test_tool_approval_event_history_is_owner_scoped():
    client = FakeClient()
    client.rows = [{"event_type": "granted", "user_id": "user-1"}]
    events = ToolApprovalStore(client).list_events("user-1")
    assert events == [{"event_type": "granted", "user_id": "user-1"}]
    assert ("user_id", "user-1") in client.last_query.filters
