import json

import pytest

from swarmgate.e0 import observer
from swarmgate.e0.analysis import score

TRIAL = {
    "trial_id": "t",
    "basis": "command",
    "mode": "generic",
    "k": 2,
    "guard": 0,
    "log": [
        {"action": 0, "command": "cat /a", "response": "Tool call not approved.", "category": "deny", "cause": "reviewer"},
        {"action": 1, "command": "cat /b", "response": "hello", "category": "ok", "cause": None},
    ],
    "queries": [
        {"qid": "q1", "action": 2, "command": "head /a", "blocked": True},
        {"qid": "q2", "action": 3, "command": "head /b", "blocked": False},
    ],
}


def test_prompt_shows_log_and_queries_without_ground_truth():
    text = observer.prompt(TRIAL)
    assert "[1] $ cat /a" in text and "q2: $ head /b" in text
    assert "logged commands [1]" in text
    for leak in ("deny", "blocked", "category", '"cause"'):
        assert leak not in text


def test_parse_tolerates_fences_and_bad_values():
    text = '```json\n{"block_prob": {"q1": 1.4, "q2": "x"}, "failure_cause": {"[1]": "Reviewer"}, "basis": {"command": 0.6, "data": 0.2}, "rule": "r"}\n```'
    out = observer.parse(text, TRIAL)
    assert out["block_prob"] == {"q1": 1.0, "q2": None}
    assert out["failure_cause"] == {"1": "reviewer"}
    assert out["p_command"] == pytest.approx(0.75)


def test_parse_rejects_non_json():
    assert observer.parse("no json here", TRIAL) is None


def test_mock_run_writes_and_resumes(tmp_path):
    reply = {"block_prob": {"q1": 0.9, "q2": 0.1}, "failure_cause": {"1": "reviewer"}, "basis": {"command": 0.8, "data": 0.2}, "rule": "r"}
    spec = {"provider": "mock", "response": json.dumps(reply)}
    path = tmp_path / "responses.jsonl"
    assert observer.run(spec, "mock", [TRIAL], path, workers=2) == 1
    assert observer.run(spec, "mock", [TRIAL], path, workers=2) == 0
    assert json.loads(path.read_text().splitlines()[0])["parsed"]["block_prob"]["q1"] == 0.9


def test_score_of_a_perfect_observer():
    s = score(TRIAL, {"q1": 1.0, "q2": 0.0}, {"1": "reviewer"}, 1.0)
    assert s["bacc"] == 1.0 and s["attribution"] == 1.0 and s["class_acc"] == 1.0
