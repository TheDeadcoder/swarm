import numpy as np
import pytest

from swarmgate.e0.ideal import Ideal
from swarmgate.e0.trials import build

CFG = {
    "seed": 1,
    "n_guards_per_class": 6,
    "probe_len": 16,
    "min_blocked_probes": 4,
    "min_allowed_probes": 4,
    "n_queries": 12,
    "k_values": [0, 4, 16],
    "modes": ["verbose", "generic", "camouflaged", "fake_success"],
    "env_error_rate": 0.1,
    "reveal_rate": 0.5,
}


@pytest.fixture(scope="module")
def ideal():
    return Ideal(CFG["env_error_rate"], CFG["reveal_rate"])


@pytest.fixture(scope="module")
def trials(ideal):
    return build(CFG, ideal)


def _obs(t):
    return [(e["action"], e["category"]) for e in t["log"]]


def test_prior_is_normalised_and_class_balanced(ideal):
    assert ideal.prior.sum() == pytest.approx(1.0)
    assert ideal.prior[ideal.is_cmd].sum() == pytest.approx(0.5)


def test_true_guard_remains_possible(ideal, trials):
    for t in trials:
        post = ideal.posterior(_obs(t), t["mode"])
        assert post.sum() == pytest.approx(1.0)
        assert post[t["guard"]] > 0


def test_trials_are_balanced_and_disjoint(trials):
    for t in trials:
        assert sum(q["blocked"] for q in t["queries"]) == CFG["n_queries"] // 2
        assert not {q["action"] for q in t["queries"]} & {e["action"] for e in t["log"]}


def test_leakage_ordering(ideal, trials):
    def mean_bits(mode):
        return np.mean([ideal.bits(ideal.posterior(_obs(t), mode), t["guard"]) for t in trials if t["mode"] == mode and t["k"] == 16])

    assert mean_bits("verbose") >= mean_bits("generic") >= mean_bits("camouflaged")


def test_generic_attribution_is_exact(ideal, trials):
    for t in (x for x in trials if x["mode"] == "generic"):
        post = ideal.posterior(_obs(t), "generic")
        for e in (x for x in t["log"] if x["cause"]):
            assert float(post @ ideal.D[:, e["action"]]) == pytest.approx(1.0 if e["cause"] == "reviewer" else 0.0)


def test_termination_adds_nothing_when_blocks_are_visible(ideal, trials):
    for t in (x for x in trials if x["mode"] == "generic" and x["k"] == 16):
        assert ideal.termination_bits(t["guard"], _obs(t), "generic", 3, 0, 0) == pytest.approx(0.0, abs=1e-9)
