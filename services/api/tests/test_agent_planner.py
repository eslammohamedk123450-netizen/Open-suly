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


@pytest.mark.parametrize("request", [
    "",
    "Build me a mobile application",
    "Search the web for current prices",
    "Analyze:",
])
def test_planner_fails_closed_for_unsupported_or_empty_requests(task_text):
    with pytest.raises(UnsupportedTaskRequest):
        plan_request(request)


def test_planner_enforces_input_size():
    with pytest.raises(UnsupportedTaskRequest, match="20,000"):
        plan_request("analyze: " + "x" * 20001)
