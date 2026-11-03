import json
import threading

from swarmgate.e0 import observer
from swarmgate.llm import Completion, is_transient

REPLY = json.dumps({"block_prob": {"q1": 0.9}, "failure_cause": {}, "basis": {"command": 1, "data": 0}, "rule": "r"})
SPEC = {"provider": "mock", "max_attempts": 3, "backoff": 0.0, "max_consecutive_failures": 2}


def trials(n):
    return [
        {"trial_id": f"t{i}", "basis": "command", "mode": "generic", "k": 0, "guard": 0, "log": [],
         "queries": [{"qid": "q1", "action": 0, "command": "cat /a", "blocked": True}]}
        for i in range(n)
    ]


class StatusError(Exception):
    def __init__(self, status):
        super().__init__(f"status {status}")
        self.status_code = status


class Flaky:
    def __init__(self, failures=0, status=429):
        self.failures, self.status, self.calls = failures, status, 0
        self.lock = threading.Lock()

    def complete(self, system, user):
        with self.lock:
            self.calls += 1
            n = self.calls
        if n <= self.failures:
            raise StatusError(self.status)
        return Completion(text=REPLY, meta={"usage": {"input": 10, "output": 5}})


def test_transient_errors_are_retried(tmp_path):
    client = Flaky(failures=2)
    stats = observer.run(SPEC, "o", trials(1), tmp_path, workers=1, client=client)
    assert stats["done"] == 1 and client.calls == 3
    assert stats["input_tokens"] == 10 and stats["output_tokens"] == 5
    assert not (tmp_path / "errors.jsonl").exists()


def test_fatal_error_stops_immediately(tmp_path):
    client = Flaky(failures=10**6, status=401)
    stats = observer.run(SPEC, "o", trials(5), tmp_path, workers=1, client=client)
    assert stats["stopped"] and stats["done"] == 0 and client.calls == 1
    assert observer.load_jsonl(tmp_path / "errors.jsonl")[0]["fatal"] is True


def test_failure_streak_stops_then_resume_completes(tmp_path):
    stats = observer.run(SPEC, "o", trials(3), tmp_path, workers=1, client=Flaky(failures=10**6, status=503))
    assert stats["stopped"] and stats["failed"] == 2 and stats["done"] == 0
    stats = observer.run(SPEC, "o", trials(3), tmp_path, workers=1, client=Flaky())
    assert stats["todo"] == 3 and stats["done"] == 3
    assert len(observer.load_responses(tmp_path / "responses.jsonl")) == 3


def test_partial_last_line_is_skipped_and_repaired(tmp_path):
    path = tmp_path / "responses.jsonl"
    path.write_text(json.dumps({"observer": "o", "trial_id": "t0", "parsed": None}) + "\n" + '{"observer": "o", "tri')
    assert len(observer.load_responses(path)) == 1
    stats = observer.run(SPEC, "o", trials(2), tmp_path, workers=1, client=Flaky())
    assert stats["todo"] == 1 and stats["done"] == 1
    assert {r["trial_id"] for r in observer.load_responses(path)} == {"t0", "t1"}


def test_duplicates_keep_latest(tmp_path):
    path = tmp_path / "responses.jsonl"
    lines = [{"observer": "o", "trial_id": "t0", "text": "a"}, {"observer": "o", "trial_id": "t0", "text": "b"}]
    path.write_text("".join(json.dumps(x) + "\n" for x in lines))
    assert [r["text"] for r in observer.load_responses(path)] == ["b"]


def test_error_classification():
    class APIConnectionError(Exception):
        pass

    assert is_transient(StatusError(429)) and is_transient(StatusError(503)) and is_transient(StatusError(529))
    assert not is_transient(StatusError(401)) and not is_transient(StatusError(400))
    assert is_transient(ConnectionError()) and is_transient(APIConnectionError())
    assert not is_transient(ValueError("bad"))
