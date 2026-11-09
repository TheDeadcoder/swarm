from pathlib import Path

import pytest
import yaml

from swarmgate.e1 import calibration, potency
from swarmgate.e1.tasks import B_TASKS, CHORES
from swarmgate.sandbox.container import Container
from tests.test_mediator import _docker_ready

CONFIG = Path(__file__).parents[1] / "configs" / "e1.yaml"


def test_calibration_covers_every_task_and_objective():
    assert set(calibration.ROUTES) == {t.id for t in B_TASKS + CHORES}
    assert set(calibration.B_NAIVE) == {t.id for t in B_TASKS}
    assert set(calibration.NAIVE) == {o.id for o in potency.OBJECTIVES}


@pytest.mark.skipif(not _docker_ready(), reason="needs Docker and the sandbox image")
def test_the_experiment_exemplar_blocks_every_naive_objective_under_g2():
    syn = yaml.safe_load(CONFIG.read_text())["syn"]
    box = Container("sg-test-calibration")
    try:
        for o in potency.OBJECTIVES:
            step, delivered, _, secrets = calibration._run(box, "syn", "G2", calibration.NAIVE[o.id], syn)
            assert not potency.achieved(o, step.output, step.allowed, delivered, secrets), o.id
    finally:
        box.close()
