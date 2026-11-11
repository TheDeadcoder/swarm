import json

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


def test_report_counts_by_objective_and_keeps_prose_out_of_strict_success(tmp_path):
    srcs = {"d|syn|A1|0": {"donor": "d", "kind": "syn", "arm": "A1", "lineage": 0}}
    rows = [{"model": "r", "cell_id": f"c{k}", "donor": "d", "kind": "syn", "arm": "A1", "lineage": 0, "objective": "S1",
             "sample": k, "action": action, "usage": {}} for k, action in enumerate(("command", "prose", "declined"))]
    (tmp_path / "responses.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    (tmp_path / "executions.jsonl").write_text(json.dumps({"cell_id": "c0", "allowed": True, "success": True}) + "\n")
    (tmp_path / battery.LENIENT).write_text(json.dumps({"cell_id": "c1", "allowed": True, "success": True}) + "\n")
    report = "\n".join(battery.report(srcs, tmp_path / "responses.jsonl", tmp_path / "executions.jsonl"))
    assert "S1 1/3" in report and "lineages 1/1" in report
    assert "0.33  0.67  1" in report
