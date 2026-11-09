from swarmgate.e1 import battery


def test_goals_cover_every_objective():
    assert sorted(battery.GOALS) == sorted(battery.BY_ID)


def test_command_strips_fences():
    assert battery.command("```bash\necho hi\n```") == "echo hi"
    assert battery.command("echo hi") == "echo hi"


def test_jobs_per_source_are_unique():
    srcs = {"k": {"donor": "d", "kind": "syn", "arm": "A1", "lineage": 0}}
    jobs = battery.jobs(srcs, "reader")
    assert len(jobs) == len(battery.GOALS) * battery.SAMPLES
    assert len({cid for _, cid, _ in jobs}) == len(jobs)
