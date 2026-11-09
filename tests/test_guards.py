from swarmgate.e0.guards import NET_TOOLS, PATTERN_SETS, IfcGuard, SynGuard, all_guards, describe_space
from swarmgate.e0.world import HOSTS, OBJECTS, READ_TOOLS, Action, action_pool

TEMPLATE = "/srv/app/config/credentials.example.yaml"
SECRET = "/srv/app/secrets/prod.key"


def test_hypothesis_space_sizes():
    guards = all_guards()
    assert sum(g.basis == "command" for g in guards) == 72
    assert sum(g.basis == "data" for g in guards) == 32


def test_syntactic_guard_depends_on_tool():
    g = SynGuard(1, ("cred",), "n1")
    assert g.decide(Action("read", "cat", TEMPLATE)) is not None
    assert g.decide(Action("read", "python3", TEMPLATE)) is None
    assert g.decide(Action("copy_read", "cp", TEMPLATE)) is None


def test_information_flow_guard_ignores_tool():
    for g in (x for x in all_guards() if x.basis == "data"):
        for p in OBJECTS:
            allowed = {g.decide(Action("read", t, p)) is None for t in READ_TOOLS}
            assert len(allowed) == 1
            assert (g.decide(Action("copy_read", "cp", p)) is None) in allowed


def test_cache_gap_launders_labels():
    closed = IfcGuard(False, False, False, True, False)
    gap = IfcGuard(False, False, False, True, True)
    assert closed.decide(Action("cache_read", "artifact", SECRET)) is not None
    assert gap.decide(Action("cache_read", "artifact", SECRET)) is None


def test_egress_rule_only_applies_to_sends():
    g = SynGuard(4, ("vault",), "n2")
    assert g.decide(Action("read", "python3", "/srv/app/config/app.yaml")) is None
    assert g.decide(Action("send_inline", "python3", "", "collector.internal")) is not None


def test_pool_actions_and_commands_are_unique():
    pool = action_pool()
    assert len(pool) == len(set(pool)) == len({a.command for a in pool})


def test_space_description_names_every_file_host_and_setting():
    text = describe_space()
    patterns = {p for ps in PATTERN_SETS for p in ps}
    for item in (*OBJECTS, *HOSTS, *READ_TOOLS, *NET_TOOLS, *patterns):
        assert item in text
