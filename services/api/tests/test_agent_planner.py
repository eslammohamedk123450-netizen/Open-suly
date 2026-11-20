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
        worker_enabled=True,
        hermes_agent_enabled=True,
        hermes_agent_isolation_confirmed=True,
        hermes_agent_base_url="http://hermes:8642",
        hermes_agent_api_key=object(),
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
        worker_enabled=True,
        hermes_agent_enabled=True,
        hermes_agent_isolation_confirmed=True,
        hermes_agent_base_url="http://hermes:8642",
        hermes_agent_api_key=object(),
    ))
    planned = plan_request("وكيل: راجع هذه المهمة")
    assert planned.steps[0]["input"]["prompt"] == "راجع هذه المهمة"


def test_agent_plan_validator_accepts_bounded_dependency_graph():
    from app.services.agent_planner import validate_agent_plan

    steps = validate_agent_plan([
        {
            "step_key": "first_step",
            "title": "First",
            "description": "",
            "depends_on": [],
            "input": {"operation": "text.analyze", "text": "first"},
        },
        {
            "step_key": "second_step",
            "title": "Second",
            "description": "Depends on first",
            "depends_on": ["first_step"],
            "input": {"operation": "text.analyze", "text": "second"},
        },
    ])
    assert steps[1]["depends_on"] == ["first_step"]


@pytest.mark.parametrize("steps", [
    [],
    [{"step_key": "first_step", "title": "First", "input": {"operation": "shell.exec"}}],
    [{"step_key": "first_step", "title": "First", "depends_on": ["missing_step"],
      "input": {"operation": "text.analyze", "text": "x"}}],
    [
        {"step_key": "first_step", "title": "First", "depends_on": ["second_step"],
         "input": {"operation": "text.analyze", "text": "x"}},
        {"step_key": "second_step", "title": "Second", "depends_on": ["first_step"],
         "input": {"operation": "text.analyze", "text": "y"}},
    ],
    [{"step_key": "first_step", "title": "First", "extra": "not allowed",
      "input": {"operation": "text.analyze", "text": "x"}}],
])
def test_agent_plan_validator_rejects_unsafe_or_invalid_dags(steps):
    from app.services.agent_planner import validate_agent_plan

    with pytest.raises(UnsupportedTaskRequest):
        validate_agent_plan(steps)


def test_agent_plan_validator_caps_step_count():
    from app.services.agent_planner import validate_agent_plan

    steps = [{
        "step_key": f"step_{index:02d}",
        "title": f"Step {index}",
        "depends_on": [],
        "input": {"operation": "text.analyze", "text": "x"},
    } for index in range(33)]
    with pytest.raises(UnsupportedTaskRequest, match="32 steps"):
        validate_agent_plan(steps)
