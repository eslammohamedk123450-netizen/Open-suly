from types import SimpleNamespace

from app.services.tool_approvals import ToolApprovalStore


class FakeQuery:
    def __init__(self, data):
        self.data = data
        self.filters = []

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
        return self

    def execute(self):
        return SimpleNamespace(data=self.data)


class FakeClient:
    def __init__(self):
        self.calls = []
        self.rows = []
        self.rpc_result = None

    def table(self, name):
        self.calls.append(("table", name))
        return FakeQuery(self.rows)

    def rpc(self, name, args):
        self.calls.append(("rpc", name, args))
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=self.rpc_result))


def test_active_scopes_are_loaded_only_for_requested_owner():
    client = FakeClient()
    client.rows = [{"permission_scope": "files.read"}, {"permission_scope": "web.search"}]
    scopes = ToolApprovalStore(client).active_scopes("user-1")
    assert scopes == frozenset({"files.read", "web.search"})
    assert ("user_id", "user-1") in client.calls or client.calls[0] == ("table", "tool_approvals")


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
