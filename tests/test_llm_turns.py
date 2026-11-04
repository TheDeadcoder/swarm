from swarmgate.llm import anthropic_messages, openai_messages

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
