import json

import httpx
import pytest

from swarmgate.llm import AdaptionClient, AdaptionError, anthropic_messages, is_transient, openai_messages, responses_input

TRANSCRIPT = [
    {"role": "user", "text": "ticket"},
    {"role": "assistant", "calls": [{"id": "t1", "command": "cat a"}]},
    {"role": "tool", "id": "t1", "output": "denied", "error": True},
    {"role": "assistant", "calls": [{"id": "t2", "command": "cat b"}]},
    {"role": "tool", "id": "t2", "output": "ok"},
    {"role": "user", "text": "write notes"},
]


def test_anthropic_rendering_keeps_tool_results_first_in_user_turns():
    m = anthropic_messages(TRANSCRIPT)
    assert [x["role"] for x in m] == ["user", "assistant", "user", "assistant", "user"]
    assert m[1]["content"] == [{"type": "tool_use", "id": "t1", "name": "shell", "input": {"command": "cat a"}}]
    assert m[2]["content"][0]["is_error"] is True
    assert [b["type"] for b in m[4]["content"]] == ["tool_result", "text"]


def test_openai_rendering_uses_tool_calls_and_tool_messages():
    m = openai_messages("sys", TRANSCRIPT)
    assert m[0] == {"role": "system", "content": "sys"}
    assert m[2]["tool_calls"][0]["function"]["arguments"] == '{"command": "cat a"}'
    assert m[3] == {"role": "tool", "tool_call_id": "t1", "content": "denied"}
    assert m[-1] == {"role": "user", "content": "write notes"}


def test_native_assistant_content_is_replayed_unchanged():
    native = [{"type": "thinking", "thinking": "", "signature": "s"}, {"type": "tool_use", "id": "t9", "name": "shell", "input": {"command": "ls"}}]
    m = anthropic_messages([{"role": "user", "text": "go"}, {"role": "assistant", "native": native, "calls": []}])
    assert m[1]["content"] is native


def test_responses_rendering_uses_function_calls_and_outputs():
    items = responses_input(TRANSCRIPT)
    assert items[0] == {"role": "user", "content": "ticket"}
    assert items[1] == {"type": "function_call", "call_id": "t1", "name": "shell", "arguments": '{"command": "cat a"}'}
    assert items[2] == {"type": "function_call_output", "call_id": "t1", "output": "denied"}
    native = [{"type": "reasoning", "id": "rs_1", "summary": []}, {"type": "function_call", "call_id": "t9", "arguments": "{}"}]
    assert responses_input([{"role": "assistant", "native": native}]) == native


def _adaption(reply: dict, status: int = 200, sent: list | None = None) -> AdaptionClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if sent is not None:
            sent.append(json.loads(request.content))
        return httpx.Response(status, json=reply)

    return AdaptionClient({"model": "m", "max_tokens": 100}, http=httpx.Client(base_url="https://x/api/v1",
                                                                               transport=httpx.MockTransport(handler)))


def test_adaption_step_parses_calls_text_and_usage():
    reply = {"status": "completed", "output": [
        {"type": "reasoning", "id": "rs_1", "summary": []},
        {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Checking."}]},
        {"type": "function_call", "call_id": "c1", "name": "shell", "arguments": '{"command": "ls /srv"}'},
        {"type": "function_call", "call_id": "c2", "name": "shell", "arguments": "not json"},
    ], "usage": {"input_tokens": 120, "output_tokens": 30, "input_tokens_details": {"cached_tokens": 100}}}
    sent = []
    turn = _adaption(reply, sent=sent).step("sys", TRANSCRIPT[:1])
    assert [(c.id, c.command) for c in turn.calls] == [("c1", "ls /srv"), ("c2", "")]
    assert turn.text == "Checking." and not turn.refused and turn.native == reply["output"]
    assert turn.meta["usage"] == {"input": 20, "output": 30, "cache_read": 100}
    body = sent[0]
    assert body["instructions"] == "sys" and body["store"] is False and body["max_output_tokens"] == 100
    assert body["tools"][0]["name"] == "shell" and body["input"] == [{"role": "user", "content": "ticket"}]


def test_adaption_refusals_and_errors():
    refusal = {"status": "completed", "output": [{"type": "message", "content": [{"type": "refusal", "refusal": "No."}]}]}
    done = _adaption(refusal).complete("sys", "merge")
    assert done.refused and done.text == "No."
    assert _adaption({"status": "incomplete", "incomplete_details": {"reason": "content_filter"}, "output": []}).step(
        "sys", TRANSCRIPT[:1]).refused
    with pytest.raises(AdaptionError) as err:
        _adaption({"error": "slow down"}, status=429).step("sys", TRANSCRIPT[:1])
    assert is_transient(err.value)
