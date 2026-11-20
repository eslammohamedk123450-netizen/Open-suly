import pytest

from app.services.agent_planner import UnsupportedTaskRequest, plan_request


@pytest.mark.parametrize("task_text", [
    "Analyze: SULY builds useful tools",
    "analyse: one two three",
    "حلل: سولي مساعد ذكي",
    "حلّل: محتوى تجريبي",
])
def test_planner_creates_only_registered_text_analysis_step(task_text):
    planned = plan_request(task_text)
    assert planned.planner == "deterministic-v1"
    assert len(planned.steps) == 1
    assert planned.steps[0]["input"]["operation"] == "text.analyze"
    assert planned.steps[0]["depends_on"] == []


@pytest.mark.parametrize("task_text", [
    "",
    "Build me a mobile application",
    "Search the web for current prices",
    "Analyze:",
])
def test_planner_fails_closed_for_unsupported_or_empty_requests(task_text):
    with pytest.raises(UnsupportedTaskRequest):
        plan_request(task_text)


def test_planner_enforces_input_size():
    with pytest.raises(UnsupportedTaskRequest, match="20,000"):
        plan_request("analyze: " + "x" * 20001)


def test_planner_creates_general_agent_step_only_when_isolated_runtime_is_enabled(monkeypatch):
    from types import SimpleNamespace
    import app.core.config as config

    monkeypatch.setattr(config, "get_settings", lambda: SimpleNamespace(
        hermes_agent_enabled=True,
        hermes_agent_isolation_confirmed=True,
    ))
    planned = plan_request("agent: Review this task and explain the safe next steps")
    assert planned.planner == "agent-routing-v1"
    assert len(planned.steps) == 1
    assert planned.steps[0]["step_key"] == "general_agent"
    assert planned.steps[0]["input"] == {
        "operation": "hermes.agent.turn",
        "prompt": "Review this task and explain the safe next steps",
    }


def test_planner_rejects_general_agent_when_runtime_is_disabled(monkeypatch):
    from types import SimpleNamespace
    import app.core.config as config

    monkeypatch.setattr(config, "get_settings", lambda: SimpleNamespace(
        hermes_agent_enabled=False,
        hermes_agent_isolation_confirmed=False,
    ))
    with pytest.raises(UnsupportedTaskRequest, match="isolated Hermes runtime"):
        plan_request("agent: perform a coding task")


def test_planner_supports_arabic_general_agent_prefix_when_enabled(monkeypatch):
    from types import SimpleNamespace
    import app.core.config as config

    monkeypatch.setattr(config, "get_settings", lambda: SimpleNamespace(
        hermes_agent_enabled=True,
        hermes_agent_isolation_confirmed=True,
    ))
    planned = plan_request("وكيل: راجع هذه المهمة")
    assert planned.steps[0]["input"]["prompt"] == "راجع هذه المهمة"
