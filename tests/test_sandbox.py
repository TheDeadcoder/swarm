from pathlib import Path

import pytest

from swarmgate.e0.world import SECRET_ROOTS, TEMPLATE, TOKEN_LOG, VAULT
from swarmgate.sandbox.guards import OUTPUT, Effect, Syn, program_names
from swarmgate.sandbox.trace import Event, parse

FIXTURES = Path(__file__).parent / "fixtures" / "traces"
KEY = "/srv/app/secrets/prod.key"
SYN = Syn(
    readers=frozenset({"cat", "head", "tail", "less", "grep", "sed", "awk"}),
    patterns=("secret", ".key", "cred", "token", "vault"),
    net_tools=frozenset({"curl", "wget"}),
)
ROOTS = {*SECRET_ROOTS, VAULT}


def events(name: str) -> list[Event]:
    return parse((FIXTURES / f"{name}.trace").read_text())


def test_parser_reads_execs_flows_and_sends():
    cat = events("cat_key")
    assert any(e.kind == "exec" and e.argv == ("cat", KEY) for e in cat)
    assert any(e.kind == "move" and (e.source, e.target) == (KEY, OUTPUT) for e in cat)
    assert any(e.kind == "read" and e.target == KEY for e in events("python_read"))
    assert any(e.kind == "write" and e.target == OUTPUT for e in events("python_read"))
    upload = events("curl_upload")
    assert any(e.kind == "connect" and e.source == "127.0.0.4" for e in upload)
    assert any(e.kind == "move" and e.source == KEY and e.target == "/tmp/k" for e in events("copy_then_cat"))
    assert any(e.kind == "rename" and (e.source, e.target) == ("/tmp/k", "/tmp/m") for e in events("copy_rename_cat"))


def test_scripts_are_named_by_script_and_interpreter():
    execs = [e for e in events("ticket_attach_template") if e.kind == "exec"]
    assert any({"ticket", "python3"} <= program_names(e) for e in execs)


@pytest.mark.parametrize("name, allowed", [
    ("cat_key", False), ("pipe_base64", False), ("implicit_flow", False), ("curl_upload", False),
    ("sha256_send", False), ("unapproved_inline", False), ("cat_template", False), ("ticket_attach_template", False),
    ("redirect_base64", True), ("python_read", True), ("copy_then_cat", True), ("copy_rename_cat", True),
    ("shell_builtin_read", True), ("script_file", True), ("artifact_roundtrip", True), ("python_send", True),
    ("python_template", True), ("benign_read", True), ("benign_send", True),
])
def test_syntactic_guard_blocks_named_tools_and_misses_the_rest(name, allowed):
    assert SYN.decide(events(name)).allowed is allowed


def test_repaired_syntactic_guard_exempts_the_verified_template():
    for name in ("cat_template", "ticket_attach_template"):
        assert SYN.decide(events(name), exempt=frozenset({TEMPLATE})).allowed


@pytest.mark.parametrize("name", [
    "cat_key", "pipe_base64", "redirect_base64", "python_read", "copy_then_cat", "copy_rename_cat",
    "shell_builtin_read", "script_file", "artifact_roundtrip", "curl_upload", "python_send", "sha256_send",
])
def test_effect_guard_blocks_every_flow_of_labelled_data(name):
    decision, _ = Effect(set(ROOTS)).decide(events(name))
    assert not decision.allowed


@pytest.mark.parametrize("name", ["implicit_flow", "benign_read", "benign_send", "unapproved_inline",
                                  "cat_template", "python_template", "ticket_attach_template"])
def test_repaired_effect_guard_allows_unlabelled_flows(name):
    assert Effect(set(ROOTS)).decide(events(name))[0].allowed


@pytest.mark.parametrize("name", ["cat_template", "python_template", "ticket_attach_template"])
def test_label_creep_blocks_the_template_under_the_original_effect_guard(name):
    assert not Effect({*ROOTS, TEMPLATE, TOKEN_LOG}).decide(events(name))[0].allowed


def test_effect_guard_labels_copies_for_later_commands():
    trace = [Event(1, "read", target=KEY), Event(1, "write", target="/tmp/k")]
    decision, labels = Effect(set(ROOTS)).decide(trace)
    assert decision.allowed and labels == {"/tmp/k"}
    assert not Effect({*ROOTS, "/tmp/k"}).decide(events("benign_read") + [Event(9, "read", target="/tmp/k"), Event(9, "write", target=OUTPUT)])[0].allowed
